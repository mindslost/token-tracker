UUID = token-tracker@jason.projects
DEST = $(HOME)/.local/share/gnome-shell/extensions/$(UUID)

.PHONY: install uninstall enable disable clean test

install:
	mkdir -p $(DEST)
	cp -r extension/* $(DEST)
	chmod +x $(DEST)/cli/token_tracker_cli.py
	@echo "Extension installed to $(DEST)"
	@echo "Please restart GNOME Shell (Alt+F2 -> r on X11, or log out and back in on Wayland) then run 'make enable'."

uninstall:
	rm -rf $(DEST)
	@echo "Extension uninstalled."

enable:
	gnome-extensions enable $(UUID)

disable:
	gnome-extensions disable $(UUID)

test:
	python3 cli/token_tracker_cli.py
