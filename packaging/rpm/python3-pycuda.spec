# This file is part of Xpra.
# Copyright (C) 2014-2021 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

#we don't want to depend on libcuda via RPM dependencies
#so that we can install NVidia drivers without using RPM packages:
%define __requires_exclude ^libcuda.*$

%define _disable_source_fetch 0
%if "%{getenv:PYTHON3}" == ""
%global python3 python3
%else
%global python3 %{getenv:PYTHON3}
%undefine __pythondist_requires
%undefine __python_requires
%endif
%define python3_sitearch %(%{python3} -Ic "from sysconfig import get_path; print(get_path('platlib').replace('/usr/local/', '/usr/'))")

%global debug_package %{nil}

%define STUBS_DIR targets/x86_64-linux/lib/stubs/
%ifarch aarch64
%define STUBS_DIR targets/sbsa-linux/lib/stubs/
%endif

Name:           %{python3}-pycuda
%if !0%{?el8}
Version:        2022.2.2
%else
Version:        2022.1
%endif
Release:        1
URL:            http://mathema.tician.de/software/pycuda
Summary:        Python3 wrapper CUDA
License:        MIT
Group:          Development/Libraries/Python
%if !0%{?el8}
Source0:        https://files.pythonhosted.org/packages/78/09/9df5358ffb74d225243b56a65ffe196de481fcd8f731f55e41f2d5d36015/pycuda-%{version}.tar.gz
%else
Source0:        https://files.pythonhosted.org/packages/2d/1f/48a3a5b2c715345e7af1e09361100bd98c3d72b4025371692ab233f523d3/pycuda-%{version}.tar.gz
%endif
BuildRoot:      %{_tmppath}/%{name}-%{version}-build
Provides:       %{python3}-pycuda

BuildRequires:  make
BuildRequires:  gcc-c++
BuildRequires:  %{python3}-devel
BuildRequires:  %{python3}-setuptools
BuildRequires:  %{python3}-numpy
BuildRequires:  boost-python3-devel
BuildRequires:  libglvnd-devel
BuildRequires:  cuda

%description
PyCUDA lets you access Nvidia‘s CUDA parallel computation API from Python.


Requires:       %{python3}-decorator
Requires:       %{python3}-numpy
Requires:       %{python3}-pytools
Requires:       %{python3}-six

Suggests:       nvidia-driver-cuda-libs

%prep
sha256=`sha256sum %{SOURCE0} | awk '{print $1}'`
%if !0%{?el8}
if [ "${sha256}" != "cd92e7246bb45ac3452955a110714112674cdf3b4a9e2f4ff25a4159c684e6bb" ]; then
%else
if [ "${sha256}" != "acd9030d93e76e60b122e33ad16bcf01bb1344f4c304dedff1cd2bffb0f313a3" ]; then
%endif
	echo "invalid checksum for %{SOURCE0}"
	exit 1
fi
%setup -q -n pycuda-%{version}

%build
CUDA=/opt/cuda
%{python3} ./configure.py \
	--cuda-enable-gl \
	--cuda-root=$CUDA \
	--cudadrv-lib-dir=%{_libdir} \
	--boost-inc-dir=%{_includedir} \
	--boost-lib-dir=%{_libdir} \
	--no-cuda-enable-curand
#	--boost-python-libname=boost_python37
#	--boost-thread-libname=boost_thread
LDFLAGS=-L$CUDA/%{STUBS_DIR} CXXFLAGS=-L$CUDA/%{STUBS_DIR} %{python3} setup.py build
#make

%install
CUDA=/opt/cuda
LDFLAGS=-L$CUDA/%{STUBS_DIR} CXXFLAGS=-L$CUDA/%{STUBS_DIR} %{python3} setup.py install --prefix=%{_prefix} --root=%{buildroot}
# RHEL stream setuptools bug?
rm -fr %{buildroot}%{python3_sitearch}/UNKNOWN-*.egg-info

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root)
%doc examples/ test/
%{python3_sitearch}/pycuda*

%changelog
%if !0%{?el8}
* Wed Dec 21 2022 Antoine Martin <antoine@xpra.org> - 2022.2.2-1
- new upstream release

* Wed Dec 21 2022 Antoine Martin <antoine@xpra.org> - 2022.2.1-1
- new upstream release

* Tue Nov 22 2022 Antoine Martin <antoine@xpra.org> - 2022.2-1
- new upstream release
- remove context cleanup failures patch (merged)
%endif
* Tue Aug 16 2022 Antoine Martin <antoine@xpra.org> - 2022.1-2
- add patch to show context cleanup failures

* Sat Jun 25 2022 Antoine Martin <antoine@xpra.org> - 2022.1-1
- new upstream release

* Sun May 02 2021 Antoine Martin <antoine@xpra.org> - 2021.1-1
- new upstream release

* Wed Feb 17 2021 Antoine Martin <antoine@xpra.org> - 2020.1-3
- verify source checksum

* Thu Jan 07 2021 Antoine Martin <antoine@xpra.org> - 2020.1-2
- add weak dependency on the driver RPM which provides libcuda

* Wed Jan 06 2021 Antoine Martin <antoine@xpra.org> - 2020.1-1
- new upstream release

* Thu Sep 26 2019 Antoine Martin <antoine@xpra.org> - 2019.1.2-2
- build only for python3

* Wed Sep 25 2019 Antoine Martin <antoine@xpra.org> - 2019.1.2-1
- build for centos8
- new upstream release

* Mon May 20 2019 Antoine Martin <antoine@xpra.org> - 2019.1-1
- new upstream release
- remove patch which has been merged

* Sun Jan 13 2019 Antoine Martin <antoine@xpra.org> - 2018.1.1-3
- add patch for releasing the GIL during init and make_context

* Sun Jan 13 2019 Antoine Martin <antoine@xpra.org> - 2018.1.1-2
- add missing python six dependency

* Tue Sep 18 2018 Antoine Martin <antoine@xpra.org> - 2018.1.1-1
- new upstream release fixing Fedora 29 builds

* Thu Aug 02 2018 Antoine Martin <antoine@xpra.org> - 2018.1-1
- new upstream release

* Wed Aug 09 2017 Antoine Martin <antoine@xpra.org> - 2017.1.1-1
- new upstream release

* Tue Jul 18 2017 Antoine Martin <antoine@xpra.org> - 2017.1-2
- build python3 variant too

* Thu Jun 01 2017 Antoine Martin <antoine@xpra.org> - 2017.1-1
- new upstream release

* Sat Dec 24 2016 Antoine Martin <antoine@xpra.org> - 2016.1.2-2
- try harder to supersede the old package name

* Fri Jul 29 2016 Antoine Martin <antoine@xpra.org> - 2016.1.2-1
- new upstream release

* Sun Jul 17 2016 Antoine Martin <antoine@xpra.org> - 2016.1.1-1
- new upstream release
- rename and obsolete old python package name

* Fri Apr 01 2016 Antoine Martin <antoine@xpra.org> - 2016.1-1
- new upstream release

* Wed Nov 04 2015 Antoine Martin <antoine@xpra.org> - 2015.1.3-1
- new upstream release

* Wed Jul 01 2015 Antoine Martin <antoine@xpra.org> - 2015.1.2-1
- new upstream release

* Wed Jun 17 2015 Antoine Martin <antoine@xpra.org> - 2015.1-1
- new upstream release

* Sun Mar 29 2015 Antoine Martin <antoine@xpra.org> - 2014.1-3
- remove dependency on libcuda so the package can be installed without using the RPM drivers

* Fri Nov 07 2014 Antoine Martin <antoine@xpra.org> - 2014.1-2
- remove curand bindings which require libcurand found in full CUDA SDK

* Wed Sep 03 2014 Antoine Martin <antoine@xpra.org> - 2014.1-1
- initial packaging
