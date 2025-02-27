# This file is part of Xpra.
# Copyright (C) 2017-2023 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

from typing import Any
from ctypes import c_int, byref, cast, POINTER
from OpenGL import GLX
from OpenGL.GL import GL_VENDOR, GL_RENDERER, glGetString

from xpra.util import envbool
from xpra.client.gl.gl_check import check_PyOpenGL_support
from xpra.x11.bindings.display_source import get_display_ptr        #@UnresolvedImport
from xpra.gtk_common.error import xsync
from xpra.gtk_common.gtk_util import set_visual
from xpra.log import Logger

log = Logger("opengl")


DOUBLE_BUFFERED = envbool("XPRA_OPENGL_DOUBLE_BUFFERED", True)


GLX_ATTRIBUTES : dict[Any,str] = {
    GLX.GLX_ACCUM_RED_SIZE      : "accum-red-size",
    GLX.GLX_ACCUM_GREEN_SIZE    : "accum-green-size",
    GLX.GLX_ACCUM_BLUE_SIZE     : "accum-blue-size",
    GLX.GLX_ACCUM_ALPHA_SIZE    : "accum-alpha-size",
    GLX.GLX_RED_SIZE            : "red-size",
    GLX.GLX_GREEN_SIZE          : "green-size",
    GLX.GLX_BLUE_SIZE           : "blue-size",
    GLX.GLX_ALPHA_SIZE          : "alpha-size",
    GLX.GLX_DEPTH_SIZE          : "depth-size",
    GLX.GLX_STENCIL_SIZE        : "stencil-size",
    GLX.GLX_BUFFER_SIZE         : "buffer-size",
    GLX.GLX_AUX_BUFFERS         : "aux-buffers",
    GLX.GLX_DOUBLEBUFFER        : "double-buffered",
    GLX.GLX_LEVEL               : "level",
    GLX.GLX_STEREO              : "stereo",
    GLX.GLX_RGBA                : "rgba",
    }


def c_attrs(props):
    attrs = []
    for k,v in props.items():
        if v is None:
            attrs += [k]
        else:
            attrs += [k, v]
    attrs += [0, 0]
    return (c_int * len(attrs))(*attrs)

def get_xdisplay() -> int:
    ptr = get_display_ptr()
    if not ptr:
        raise RuntimeError("no X11 display registered")
    # pylint: disable=import-outside-toplevel
    from OpenGL.raw.GLX._types import struct__XDisplay
    return cast(ptr, POINTER(struct__XDisplay))


class GLXWindowContext:

    def __init__(self, glx_context, xid : int):
        self.context = glx_context
        self.xid = xid
        self.xdisplay : int = get_xdisplay()
        self.valid : bool = False

    def __enter__(self):
        log("glXMakeCurrent: xid=%#x, context=%s", self.xid, self.context)
        with xsync:
            if not GLX.glXMakeCurrent(self.xdisplay, self.xid, self.context):
                raise RuntimeError("glXMakeCurrent failed")
        self.valid = True

    def __exit__(self, *_args):
        self.valid = False
        if self.context:
            context_type = type(self.context)
            null_context = cast(0, context_type)
            log("glXMakeCurrent: NULL for xid=%#x", self.xid)
            if not GLX.glXMakeCurrent(self.xdisplay, 0, null_context):
                log.error("Error: glXMakeCurrent NULL failed")

    def update_geometry(self) -> None:
        """ not needed on X11 """

    def swap_buffers(self) -> None:
        assert self.valid, "GLX window context is no longer valid"
        GLX.glXSwapBuffers(self.xdisplay, self.xid)

    def __repr__(self):
        return "GLXWindowContext(%#x)" % self.xid


class GLXContext:

    def __init__(self, alpha:bool=False):
        self.props : dict[str,Any] = {}
        self.xdisplay : int = 0
        self.context = None
        self.bit_depth : int = 0
        import gi
        gi.require_version("Gdk", "3.0")  # @UndefinedVariable
        from gi.repository import Gdk  # @UnresolvedImport
        display = Gdk.Display.get_default()
        if not display:
            log.warn("Warning: GLXContext: no default display")
            return
        screen = display.get_default_screen()
        if not screen:
            log.warn("Warning: GLXContext: no default screen")
            return
        bpc : int = 8
        pyattrs = {
            GLX.GLX_RGBA            : None,
            GLX.GLX_RED_SIZE        : bpc,
            GLX.GLX_GREEN_SIZE      : bpc,
            GLX.GLX_BLUE_SIZE       : bpc,
            }
        if alpha:
            pyattrs[GLX.GLX_ALPHA_SIZE] = int(alpha)*bpc
        if DOUBLE_BUFFERED:
            pyattrs[GLX.GLX_DOUBLEBUFFER] = None
        attrs = c_attrs(pyattrs)
        self.xdisplay = get_xdisplay()
        xvinfo = GLX.glXChooseVisual(self.xdisplay, screen.get_number(), attrs)
        def getconfig(attrib):
            value = c_int()
            r = GLX.glXGetConfig(self.xdisplay, xvinfo, attrib, byref(value))
            assert r==0, "glXGetConfig returned %i" % r
            return value.value
        assert getconfig(GLX.GLX_USE_GL), "OpenGL is not supported by this visual!"
        major = c_int()
        minor = c_int()
        assert GLX.glXQueryVersion(self.xdisplay, byref(major), byref(minor))
        log("found GLX version %i.%i", major.value, minor.value)
        self.props["GLX"] = (major.value, minor.value)
        self.bit_depth = sum(getconfig(x) for x in (
            GLX.GLX_RED_SIZE, GLX.GLX_GREEN_SIZE, GLX.GLX_BLUE_SIZE, GLX.GLX_ALPHA_SIZE))
        self.props["depth"] = self.bit_depth
        #hide those because we don't use them
        #and because they're misleading: 'has-alpha' may be False
        #even when we have RGBA support (and therefore very likely to have alpha..)
        #self.props["has-depth-buffer"] = getconfig(GLX.GLX_DEPTH_SIZE)>0
        #self.props["has-stencil-buffer"] = getconfig(GLX.GLX_STENCIL_SIZE)>0
        #self.props["has-alpha"] = getconfig(GLX.GLX_ALPHA_SIZE)>0
        for attrib,name in GLX_ATTRIBUTES.items():
            v = getconfig(attrib)
            if name in ("stereo", "double-buffered", "rgba"):
                v = bool(v)
            self.props[name] = v
        #attribute names matching gtkgl:
        display_mode = []
        if getconfig(GLX.GLX_RGBA):
            #this particular context may not have alpha channel support...
            #but if we have RGBA then it's almost guaranteed that we can do ALPHA
            display_mode.append("ALPHA")
        if getconfig(GLX.GLX_DOUBLEBUFFER):
            display_mode.append("DOUBLE")
        else:   # pragma: no cover
            display_mode.append("SINGLE")
        self.props["display_mode"] = display_mode
        self.context = GLX.glXCreateContext(self.xdisplay, xvinfo, None, True)
        self.props["direct"] = bool(GLX.glXIsDirect(self.xdisplay, self.context))
        def getstr(k) -> str:
            try:
                return glGetString(k)
            except Exception as e:  # pragma: no cover
                self.props["safe"] = False
                result = getattr(e, "result", None)
                if result and isinstance(result, str):
                    return result
                raise
        self.props["vendor"] = getstr(GL_VENDOR)
        self.props["renderer"] = getstr(GL_RENDERER)
        log("GLXContext(%s) context=%s, props=%s", alpha, self.context, self.props)

    def check_support(self, force_enable:bool=False) -> dict[str,Any]:
        i = self.props
        if not self.xdisplay:
            return {
                "success"   : False,
                "safe"      : False,
                "enabled"   : False,
                "message"   : "cannot access X11 display",
                }
        import gi
        gi.require_version("Gtk", "3.0")  # @UndefinedVariable
        from gi.repository import Gtk  # @UnresolvedImport
        tmp = Gtk.Window(Gtk.WindowType.TOPLEVEL)
        tmp.resize(1, 1)
        tmp.set_decorated(False)
        tmp.realize()
        da = Gtk.DrawingArea()
        tmp.add(da)
        set_visual(da, True)
        win = tmp.get_window()
        log("check_support(%s) using temporary window=%s", force_enable, tmp)
        with self.get_paint_context(win):
            i.update(check_PyOpenGL_support(force_enable))
        tmp.destroy()
        return i

    def get_bit_depth(self) -> int:
        return self.bit_depth

    def is_double_buffered(self) -> bool:
        return DOUBLE_BUFFERED

    def get_paint_context(self, gdk_window) -> GLXWindowContext:
        assert self.context and gdk_window
        return GLXWindowContext(self.context, gdk_window.get_xid())

    def destroy(self) -> None:
        c = self.context
        if c:
            self.context = None
            GLX.glXDestroyContext(self.xdisplay, c)

    def __repr__(self):
        return f"GLXContext({self.props})"

GLContext = GLXContext


def check_support() -> dict[str,Any]:
    ptr = get_display_ptr()
    if not ptr:
        from xpra.x11.gtk3.gdk_display_source import init_gdk_display_source    #@UnresolvedImport, @UnusedImport
        init_gdk_display_source()

    return GLContext().check_support()
