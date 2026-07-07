import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const TokenTrackerButton = GObject.registerClass(
    { GTypeName: 'TokenTrackerButton' },
    class TokenTrackerButton extends PanelMenu.Button {
        _init(extension) {
            super._init(0.0, 'Token Tracker');
            this.extension = extension;
            
            // Set up icon
            const iconPath = this.extension.path + '/icons/token-tracker-symbolic.svg';
            this._icon = new St.Icon({
                gicon: Gio.icon_new_for_string(iconPath),
                style_class: 'system-status-icon'
            });
            this.add_child(this._icon);

            // Create container for dropdown elements
            this._menuBox = new St.BoxLayout({
                vertical: true,
                style: 'min-width: 260px;'
            });
            
            const section = new PopupMenu.PopupMenuSection();
            section.actor.add_child(this._menuBox);
            this.menu.addMenuItem(section);

            // Set up initial state variables
            this._pollTimeoutId = 0;
            this._isRefreshing = false;

            // Populate initial empty/loading UI
            this._buildInitialUI();
        }

        _buildInitialUI() {
            this._menuBox.destroy_all_children();

            // Header Row
            const headerBox = new St.BoxLayout({
                vertical: true,
                style_class: 'token-tracker-header-box'
            });
            
            const titleLabel = new St.Label({
                text: 'Token Tracker',
                style_class: 'token-tracker-header'
            });
            headerBox.add_child(titleLabel);

            this._statusLabel = new St.Label({
                text: 'Connecting to helper...',
                style_class: 'token-tracker-sub'
            });
            headerBox.add_child(this._statusLabel);
            this._menuBox.add_child(headerBox);

            // Dynamic content box
            this._quotaContainer = new St.BoxLayout({
                vertical: true
            });
            this._menuBox.add_child(this._quotaContainer);

            // Footer
            const footerBox = new St.BoxLayout({
                vertical: false,
                style_class: 'token-tracker-footer',
                style: 'align-items: center;'
            });

            this._refreshButton = new St.Button({
                style_class: 'token-tracker-refresh-button',
                can_focus: true,
                child: new St.Icon({
                    icon_name: 'view-refresh-symbolic',
                    icon_size: 16
                })
            });
            this._refreshButton.connect('clicked', () => {
                this.updateData();
            });
            footerBox.add_child(this._refreshButton);

            this._updatedLabel = new St.Label({
                text: 'Never updated',
                style_class: 'token-tracker-bucket-details',
                x_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
                style: 'text-align: right;'
            });
            footerBox.add_child(this._updatedLabel);

            this._menuBox.add_child(footerBox);
        }

        startPoll() {
            // Immediately fetch first set of data
            this.updateData();

            // Start 15-minute polling interval (900 seconds)
            this._pollTimeoutId = GLib.timeout_add_seconds(
                GLib.PRIORITY_DEFAULT,
                900,
                () => {
                    this.updateData();
                    return GLib.SOURCE_CONTINUE;
                }
            );
        }

        stopPoll() {
            if (this._pollTimeoutId > 0) {
                GLib.Source.remove(this._pollTimeoutId);
                this._pollTimeoutId = 0;
            }
        }

        updateData() {
            if (this._isRefreshing) {
                return;
            }
            this._isRefreshing = true;
            this._statusLabel.set_text('Refreshing data...');
            this._refreshButton.set_reactive(false);

            // Execute the python CLI script asynchronously
            const cliPath = this.extension.path + '/cli/token_tracker_cli.py';
            const file = Gio.File.new_for_path(cliPath);
            if (!file.query_exists(null)) {
                this._handleError('CLI helper script not found.');
                return;
            }

            try {
                const proc = new Gio.Subprocess({
                    argv: ['python3', cliPath],
                    flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
                });
                
                proc.init(null);
                proc.communicate_utf8_async(null, null, (obj, res) => {
                    try {
                        const [success, stdout, stderr] = obj.communicate_utf8_finish(res);
                        if (!success || !stdout) {
                            this._handleError(stderr || 'CLI execution failed.');
                            return;
                        }
                        
                        const data = JSON.parse(stdout);
                        this._refreshUI(data);
                    } catch (e) {
                        this._handleError(e.message);
                    } finally {
                        this._isRefreshing = false;
                        this._refreshButton.set_reactive(true);
                    }
                });
            } catch (e) {
                this._handleError(e.message);
                this._isRefreshing = false;
                this._refreshButton.set_reactive(true);
            }
        }

        _refreshUI(data) {
            this._quotaContainer.destroy_all_children();

            if (data.status !== 'connected') {
                this._handleError(data.error || 'Disconnected from helper.');
                return;
            }

            this._statusLabel.set_text(`${data.email} (${data.plan})`);

            // Update timestamp
            const now = new Date();
            const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            this._updatedLabel.set_text(`Updated at ${timeStr}`);

            if (!data.groups || data.groups.length === 0) {
                const noDataLabel = new St.Label({
                    text: 'No active quotas found.',
                    style_class: 'token-tracker-bucket-details',
                    style: 'padding: 10px;'
                });
                this._quotaContainer.add_child(noDataLabel);
                return;
            }

            for (const group of data.groups) {
                const groupBox = new St.BoxLayout({
                    vertical: true,
                    style_class: 'token-tracker-group'
                });

                const groupTitle = new St.Label({
                    text: group.name,
                    style_class: 'token-tracker-group-title'
                });
                groupBox.add_child(groupTitle);

                for (const bucket of group.buckets) {
                    const bucketBox = new St.BoxLayout({
                        vertical: true,
                        style_class: 'token-tracker-bucket-row'
                    });

                    // Row containing Name and remaining fraction
                    const labelRow = new St.BoxLayout({
                        vertical: false,
                        style_class: 'token-tracker-bucket-header'
                    });

                    const bucketName = new St.Label({
                        text: bucket.name,
                        style_class: 'token-tracker-bucket-name',
                        x_expand: true
                    });
                    labelRow.add_child(bucketName);

                    let fraction = bucket.remaining_fraction !== null ? bucket.remaining_fraction : 1.0;
                    fraction = Math.max(0.0, Math.min(1.0, fraction));
                    const percent = Math.round(fraction * 100);
                    const percentLabel = new St.Label({
                        text: `${percent}%`,
                        style_class: 'token-tracker-bucket-fraction'
                    });
                    labelRow.add_child(percentLabel);
                    bucketBox.add_child(labelRow);

                    // Progress Bar
                    const progressBg = new St.BoxLayout({
                        style_class: 'token-tracker-progress-bg'
                    });
                    
                    let fillClass = 'token-tracker-progress-fill';
                    if (fraction < 0.4) {
                        fillClass += ' danger';
                    } else if (fraction <= 0.7) {
                        fillClass += ' warning';
                    }

                    const progressFill = new St.Widget({
                        style_class: fillClass
                    });
                    progressBg.add_child(progressFill);

                    // Dynamically update fill width when background is allocated/resized
                    progressBg.connect('notify::width', () => {
                        const bgWidth = progressBg.width;
                        if (bgWidth > 0) {
                            progressFill.width = Math.round(bgWidth * fraction);
                        }
                    });

                    bucketBox.add_child(progressBg);

                    // Detail text (resets in...)
                    if (bucket.description) {
                        const details = new St.Label({
                            text: bucket.description,
                            style_class: 'token-tracker-bucket-details'
                        });
                        bucketBox.add_child(details);
                    } else if (bucket.reset_time) {
                        // Format countdown from ISO reset_time
                        const countdown = this._getCountdownText(bucket.reset_time);
                        const details = new St.Label({
                            text: `Resets in ${countdown}`,
                            style_class: 'token-tracker-bucket-details'
                        });
                        bucketBox.add_child(details);
                    }

                    groupBox.add_child(bucketBox);
                }

                this._quotaContainer.add_child(groupBox);
            }
        }

        _handleError(errorMessage) {
            this._statusLabel.set_text('Disconnected');
            this._quotaContainer.destroy_all_children();

            const errorLabel = new St.Label({
                text: errorMessage,
                style_class: 'token-tracker-bucket-details',
                style: 'color: #c01c28; padding: 10px; min-width: 240px; text-wrap: wrap;'
            });
            this._quotaContainer.add_child(errorLabel);
            this._updatedLabel.set_text('Update failed');
        }

        _getCountdownText(isoTimeString) {
            try {
                const target = Date.parse(isoTimeString);
                const diff = target - Date.now();
                if (diff <= 0) {
                    return 'refreshing...';
                }
                const hours = Math.floor(diff / (1000 * 60 * 60));
                const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                
                if (hours > 24) {
                    const days = Math.floor(hours / 24);
                    const remainingHours = hours % 24;
                    return `${days}d, ${remainingHours}h`;
                } else if (hours > 0) {
                    return `${hours}h, ${mins}m`;
                } else {
                    return `${mins}m`;
                }
            } catch (e) {
                return 'unknown';
            }
        }
    }
);

export default class TokenTrackerExtension extends Extension {
    enable() {
        this._indicator = new TokenTrackerButton(this);
        Main.panel.addToStatusArea('token-tracker-indicator', this._indicator);
        this._indicator.startPoll();
    }

    disable() {
        if (this._indicator) {
            this._indicator.stopPoll();
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
