PREFIX ?= /usr
SYSCONFDIR ?= /etc
DESTDIR ?=
PYTHON ?= python3

LIBDIR = $(DESTDIR)$(PREFIX)/lib/glue-apps
SHAREDIR = $(DESTDIR)$(PREFIX)/share

.PHONY: all test install uninstall

all:

test:
	$(PYTHON) -m unittest discover -s tests

install:
	install -Dm755 glue-apps $(DESTDIR)$(PREFIX)/bin/glue-apps
	install -dm755 $(LIBDIR)/glue_apps
	install -m644 glue_apps/*.py $(LIBDIR)/glue_apps/
	install -Dm755 helpers/pkg.sh $(LIBDIR)/pkg.sh
	install -Dm755 helpers/update.sh $(LIBDIR)/update.sh
	install -Dm755 helpers/update-check.sh $(LIBDIR)/update-check.sh
	install -Dm755 helpers/unlock.sh $(LIBDIR)/unlock.sh
	install -Dm644 polkit/org.glue.apps.policy $(SHAREDIR)/polkit-1/actions/org.glue.apps.policy
	install -Dm644 data/applications/org.glue.Apps.desktop $(SHAREDIR)/applications/org.glue.Apps.desktop
	install -Dm644 data/icons/org.glue.Apps.svg $(SHAREDIR)/icons/hicolor/scalable/apps/org.glue.Apps.svg
	install -Dm644 data/apps.conf $(DESTDIR)$(SYSCONFDIR)/glue/apps.conf
	cd data && find themes -type f -exec install -Dm644 {} $(SHAREDIR)/glue-apps/{} \;
	install -Dm644 LICENSE $(SHAREDIR)/licenses/glue-apps/LICENSE

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/glue-apps
	rm -rf $(LIBDIR) $(SHAREDIR)/glue-apps
	rm -f $(SHAREDIR)/polkit-1/actions/org.glue.apps.policy
	rm -f $(SHAREDIR)/applications/org.glue.Apps.desktop
	rm -f $(SHAREDIR)/icons/hicolor/scalable/apps/org.glue.Apps.svg
