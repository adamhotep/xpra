# -*- coding: utf-8 -*-
# This file is part of Xpra.
# Copyright (C) 2010-2023 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

from typing import Any

from xpra.os_util import POSIX, OSX, bytestostr
from xpra.util import envint, csv, typedict
from xpra.server.source.stub_source_mixin import StubSourceMixin
from xpra.log import Logger

log = Logger("webcam")

MAX_WEBCAM_DEVICES = envint("XPRA_MAX_WEBCAM_DEVICES", 1)


def valid_encodings(args):
    #ensure that the encodings specified can be validated using HEADERS
    try:
        from xpra.codecs.pillow.decoder import HEADERS  # pylint: disable=import-outside-toplevel
    except ImportError:
        return []
    encodings = []
    for x in args:
        x = bytestostr(x)
        if x not in HEADERS.values():
            log.warn("Warning: %s is not supported for webcam forwarding", x)
        else:
            encodings.append(x)
    return encodings


class WebcamMixin(StubSourceMixin):
    """
    Handle webcam forwarding.
    """

    @classmethod
    def is_needed(cls, caps : typedict) -> bool:
        #the 'webcam' capability was only added in v4,
        #so we have to enable the mixin by default:
        if not caps.boolget("webcam", True):
            return False
        try:
            from xpra.codecs.pillow.decoder import HEADERS  # pylint: disable=import-outside-toplevel
            assert HEADERS
        except ImportError:
            return False
        return True

    def __init__(self):
        self.webcam_enabled = False
        self.webcam_device = None
        self.webcam_encodings = []

    def init_from(self, _protocol, server) -> None:
        self.webcam_enabled     = server.webcam_enabled
        self.webcam_device      = server.webcam_device
        self.webcam_encodings   = valid_encodings(server.webcam_encodings)
        log("WebcamMixin: enabled=%s, device=%s, encodings=%s",
            self.webcam_enabled, self.webcam_device, self.webcam_encodings)

    def init_state(self) -> None:
        #for each webcam device_id, the actual device used
        self.webcam_forwarding_devices : dict = {}

    def cleanup(self) -> None:
        self.stop_all_virtual_webcams()


    def get_info(self) -> dict[str,Any]:
        return {
            "webcam" : {
                "encodings"         : self.webcam_encodings,
                "active-devices"    : len(self.webcam_forwarding_devices),
                }
            }


    def get_device_options(self, device_id : int) -> dict[Any,Any]:  #pylint: disable=unused-argument
        if not POSIX or OSX or not self.webcam_enabled:
            return {}
        if self.webcam_device:
            #use the device specified:
            return {
                0 : {
                    "device" : self.webcam_device,
                    },
                   }
        from xpra.platform.posix.webcam import get_virtual_video_devices  # pylint: disable=import-outside-toplevel
        return get_virtual_video_devices()


    def send_webcam_ack(self, device, frame:int, *args) -> None:
        self.send_async("webcam-ack", device, frame, *args)

    def send_webcam_stop(self, device, message) -> None:
        self.send_async("webcam-stop", device, message)


    def start_virtual_webcam(self, device_id, w:int, h:int) -> bool:
        log("start_virtual_webcam%s", (device_id, w, h))
        assert w>0 and h>0
        webcam = self.webcam_forwarding_devices.get(device_id)
        if webcam:
            log.warn("Warning: virtual webcam device %s already in use,", device_id)
            log.warn(" stopping it first")
            self.stop_virtual_webcam(device_id)
        def fail(msg):
            log.error("Error: cannot start webcam forwarding")
            log.error(" %s", msg)
            self.send_webcam_stop(device_id, msg)
        if not self.webcam_enabled:
            fail("webcam forwarding is disabled")
            return False
        devices = self.get_device_options(device_id)
        if not devices:
            fail("no virtual devices found")
            return False
        if len(self.webcam_forwarding_devices)>MAX_WEBCAM_DEVICES:
            ndev = len(self.webcam_forwarding_devices)
            fail(f"too many virtual devices are already in use: {ndev}")
            return False
        errs = {}
        for vid, device_info in devices.items():
            log("trying device %s: %s", vid, device_info)
            device_str = device_info.get("device")
            try:
                from xpra.codecs.v4l2.pusher import Pusher, get_input_colorspaces    #@UnresolvedImport pylint: disable=import-outside-toplevel
                in_cs = get_input_colorspaces()
                p = Pusher()
                src_format = in_cs[0]
                p.init_context(w, h, w, src_format, device_str)
                self.webcam_forwarding_devices[device_id] = p
                log.info("webcam forwarding using %s", device_str)
                #this tell the client to start sending, and the size to use - which may have changed:
                self.send_webcam_ack(device_id, 0, p.get_width(), p.get_height())
                return True
            except Exception as e:
                log.error("Error: failed to start virtual webcam")
                log.error(" using device %s: %s", vid, device_info, exc_info=True)
                errs[device_str] = str(e)
                del e
        fail("all devices failed")
        if len(errs)>1:
            log.error(" tried %i devices:", len(errs))
        for device_str, err in errs.items():
            log.error(" %s : %s", device_str, err)
        return False

    def stop_all_virtual_webcams(self) -> None:
        log("stop_all_virtual_webcams() stopping: %s", self.webcam_forwarding_devices)
        for device_id in tuple(self.webcam_forwarding_devices.keys()):
            self.stop_virtual_webcam(device_id)

    def stop_virtual_webcam(self, device_id, message="") -> None:
        webcam = self.webcam_forwarding_devices.pop(device_id, None)
        log("stop_virtual_webcam(%s, %s) webcam=%s", device_id, message, webcam)
        if not webcam:
            log.warn("Warning: cannot stop webcam device %s: no such context!", device_id)
            return
        try:
            webcam.clean()
        except Exception as e:
            log.error("Error stopping virtual webcam device: %s", e)
            log("%s.clean()", exc_info=True)

    def process_webcam_frame(self, device_id, frame_no:int, encoding:str, w:int, h:int, data) -> bool:
        webcam = self.webcam_forwarding_devices.get(device_id)
        log("process_webcam_frame: device %s, frame no %i: %s %ix%i, %i bytes, webcam=%s",
            device_id, frame_no, encoding, w, h, len(data), webcam)
        assert encoding and w and h and data
        if not webcam:
            log.error("Error: webcam forwarding is not active, dropping frame")
            self.send_webcam_stop(device_id, "not started")
            return False
        try:
            # pylint: disable=import-outside-toplevel
            from xpra.codecs.pillow.decoder import open_only
            if encoding not in self.webcam_encodings:
                raise ValueError(f"invalid encoding specified: {encoding} (must be one of {self.webcam_encodings})")
            rgb_pixel_format = "BGRX"       #BGRX
            img = open_only(data, (encoding,))
            pixels = img.tobytes("raw", rgb_pixel_format)
            from xpra.codecs.image_wrapper import ImageWrapper
            bgrx_image = ImageWrapper(0, 0, w, h, pixels, rgb_pixel_format, 32, w*4, planes=ImageWrapper.PACKED)
            src_format = webcam.get_src_format()
            if not src_format:
                #closed / closing
                return False
            #one of those two should be present
            try:
                csc_mod = "csc_libyuv"
                from xpra.codecs.libyuv.colorspace_converter import (   #@UnresolvedImport
                    get_input_colorspaces,
                    get_output_colorspaces,
                    ColorspaceConverter,
                    )
            except ImportError:
                self.send_webcam_stop(device_id, "no csc module")
                return False
            try:
                if rgb_pixel_format not in get_input_colorspaces():
                    raise ValueError(f"unsupported RGB pixel format {rgb_pixel_format}")
                if src_format not in get_output_colorspaces(rgb_pixel_format):
                    raise ValueError(f"unsupported output colourspace format {src_format}")
            except Exception as e:
                log.error("Error: cannot convert %s to %s using %s:", rgb_pixel_format, src_format, csc_mod)
                log.estr(e)
                log.error(" input-colorspaces: %s", csv(get_input_colorspaces()))
                log.error(" output-colorspaces: %s", csv(get_output_colorspaces(rgb_pixel_format)))
                self.send_webcam_stop(device_id, f"csc format error: {e}")
                return False
            tw = webcam.get_width()
            th = webcam.get_height()
            csc = ColorspaceConverter()
            csc.init_context(w, h, rgb_pixel_format, tw, th, src_format)
            image = csc.convert_image(bgrx_image)
            webcam.push_image(image)
            #tell the client all is good:
            self.send_webcam_ack(device_id, frame_no)
            return True
        except Exception as e:
            log("error on %ix%i frame %i using encoding %s", w, h, frame_no, encoding, exc_info=True)
            log.error("Error processing webcam frame:")
            msg = str(e)
            if not msg:
                msg = "unknown error"
                log.error(f" {webcam} error", exc_info=True)
            log.error(" %s", msg)
            self.send_webcam_stop(device_id, msg)
            self.stop_virtual_webcam(device_id)
            return False
