# scipy
#
# TMPPREFIX contains prebuild f2c/f77 command.  TMPPYTHON is a copy of
# numpy with additional fcompiler class to support f2c.

NAME = scipy
VERSION = 0.13.0b1

TMPPYTHON = $(OBJROOT)/Python
PP := $(PYTHONPATH)
override PYTHONPATH := $(TMPPYTHON):$(PYTHONPATH)
export PYTHONPATH
override PATH := $(TMPPREFIX)/bin:$(PATH)
export PATH
export CFLAGS=-Wno-implicit-function-declaration

include ../Makefile.inc

NUMPY = $(TMPPYTHON)/numpy
FCOMPILER = $(NUMPY)/distutils/fcompiler

custompatching:
	@echo PATH=$$PATH
	@echo PYTHONPATH=$$PYTHONPATH
	@set -x && \
	for f in $(DIR)/scipy/integrate/quadpack/*.f; do \
	    ed - $$f < add_localauto_arg.ed || exit 1; \
	done
	#ed - $(DIR)/scipy/lib/blas/fblas_l1.pyf.src < scipy_lib_blas_fblas_l1.pyf.src.ed
	#ed - $(DIR)/scipy/linalg/fblas_l1.pyf.src < scipy_linalg_fblas_l1.pyf.src.ed
	ed - $(DIR)/scipy/sparse/linalg/eigen/arpack/ARPACK/FWRAPPERS/wrap_veclib_c.c < veclib_cabi_c.c.ed
	ed - $(DIR)/scipy/sparse/linalg/isolve/iterative/FWRAPPERS/veclib_cabi_c.c < veclib_cabi_c.c.ed
	ed - $(DIR)/scipy/sparse/linalg/isolve/iterative/FWRAPPERS/wrap_veclib_c.c < veclib_cabi_c.c.ed
	ed - $(DIR)/scipy/stats/mvn.pyf < scipy_stats_mvn.pyf.ed
	ed - $(DIR)/scipy/stats/mvndst.f < scipy_stats_mvndst.f.ed
	sed -e 's,@SDKROOT@,$(SDKROOT),g' -e 's,@INCLUDEPYTHONVERS@,$(INCLUDEPYTHONVERS),g' $(SRCROOT)/Modules/setup.py-config.ed | ed - $(DIR)/setup.py
	sed 's,XXXXX,$(TMPPREFIX),' setup.cfg >> $(DIR)/setup.cfg
	mkdir -p $(TMPPYTHON)
	ditto $(PP)/numpy $(NUMPY)
	cp f2c.py $(FCOMPILER)
	ed - $(FCOMPILER)/__init__.py < numpy_distutils_fcompiler___init__.py.ed
	( cd $(DIR) ; patch -p1 ) < 103310602-compilier-fixes.diff

postinstall:
	cp -f $(DIR)/LICENSE.txt $(OSL)/$(NAME)-$(VERSION).txt
	cp -f $(NAME).partial $(OSV)/$(NAME)-$(VERSION).partial
