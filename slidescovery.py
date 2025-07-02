import sys
import os
import random
import shutil
import json
import re
import send2trash
import subprocess
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QFileDialog, QSizeGrip, QPushButton, QHBoxLayout, QMenu, 
                             QTextEdit, QSplitter, QRadioButton, QButtonGroup, 
                             QTreeView, QMessageBox, QInputDialog, QLineEdit, QAbstractItemView)
from PyQt6.QtCore import QTimer, Qt, QPoint, QSize, QDir, QStandardPaths
from PyQt6.QtGui import (QPixmap, QMouseEvent, QResizeEvent, QKeyEvent, QAction, 
                         QFileSystemModel, QWheelEvent, QTextCursor, QTextCharFormat, QColor, QTextDocument, QIcon)
from PIL import Image # Pillow library

class ImageLabel(QLabel):
    """
    Custom QLabel to handle mouse events specifically for the image display area.

    This application uses third-party libraries.
    - PyQt6: Licensed under the GPLv3.
    - Pillow: Licensed under the HPND License.
    - send2trash: Licensed under the BSD License.
    Please see the LICENSE.txt file for more details.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_widget = parent
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event: QMouseEvent):
        # Right-click to open in explorer
        if event.button() == Qt.MouseButton.RightButton:
            if self.parent_widget.image_files and self.parent_widget.current_index < len(self.parent_widget.image_files):
                current_image_path = self.parent_widget.image_files[self.parent_widget.current_index]
                try:
                    subprocess.Popen(f'explorer /select,"{current_image_path}"')
                except FileNotFoundError:
                    self.parent_widget.show_feedback("Could not open explorer.")
        else:
            # Allow the main window to handle dragging
            self.parent_widget.mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.parent_widget.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.parent_widget.mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # Double-click to toggle fullscreen
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_widget.toggle_maximize_restore()

class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_widget = parent
        self.old_pos = None
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)
        layout.setSpacing(5)

        self.title_label = QLabel("Slidescovery", self)
        self.title_label.setStyleSheet("color: white; font-weight: bold;")

        self.fav_button = self.parent_widget.create_button("♥", self.parent_widget.add_to_favorites, "Favorite (Space)")
        self.like_button = self.parent_widget.create_button("★", self.parent_widget.add_to_likes, "Like (2)")
        self.info_button = self.parent_widget.create_button("ℹ️", self.parent_widget.toggle_info_pane, "Toggle Info (I)")
        self.settings_button = self.parent_widget.create_button("⚙️", self.parent_widget.open_settings_menu, "Settings")
        
        # Window control buttons
        self.minimize_button = self.parent_widget.create_button("_", self.parent_widget.showMinimized, "Minimize")
        self.maximize_restore_button = self.parent_widget.create_button("🗗", self.parent_widget.toggle_maximize_restore, "Maximize/Restore")
        self.close_button = self.parent_widget.create_button("✕", self.parent_widget.close, "Close")

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.fav_button)
        layout.addWidget(self.like_button)
        layout.addWidget(self.info_button)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_restore_button)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.parent_widget.move(self.parent_widget.x() + delta.x(), self.parent_widget.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.old_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_widget.toggle_maximize_restore()

class SlideshowWidget(QWidget):
    def __init__(self):
        super().__init__()
        # --- Attributes ---
        self.CONFIG_FILE = self.get_config_path()
        self.source_folder, self.favorites_folder, self.likes_folder = None, None, None
        self.current_pixmap = None
        self.image_files, self.current_index, self.is_paused = [], 0, False
        self.current_sort_order = "random"
        self.current_sort_direction = "asc" # New attribute for sort direction
        self.slideshow_interval = 5000
        self.confirm_delete = True
        self.skip_non_matching = False
        self.info_panel_visible = False
        self.is_skipping = False
        self.old_pos = None
        self.feedback_position = 'center' # To store current feedback position

        # --- Initialization ---
        self.init_ui()
        self.load_settings()

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.show_next_image(manual=False))

        if self.source_folder and os.path.exists(self.source_folder):
            self._set_tree_view_root() # Call helper to set up tree view
            self.load_images(self.source_folder)
            self.apply_sorting()
            self.current_index = 0
            self.start_slideshow()
        else:
            self.prompt_for_folder('source')

    def get_config_path(self):
        path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        app_dir = os.path.join(path, "Slidescovery")
        if not os.path.exists(app_dir):
            os.makedirs(app_dir)
        return os.path.join(app_dir, "slideshow_config.json")

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(150, 150, 1200, 700)
        self.setWindowTitle('Slidescovery')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget(self)
        container.setStyleSheet("background-color: rgba(20, 20, 20, 230); border-radius: 10px;")
        self.main_layout.addWidget(container)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 8, 8, 8)

        self.title_bar = TitleBar(self)
        container_layout.addWidget(self.title_bar)

        top_controls_layout = QHBoxLayout()
        self.tree_toggle_button = self.create_button("<<", self.toggle_tree_view, "Toggle Tree View")
        top_controls_layout.addWidget(self.tree_toggle_button)
        top_controls_layout.addStretch()

        self.radio_group = QButtonGroup(self)
        self.radio_group.buttonToggled.connect(self.on_sort_order_changed)
        self.radio_random = self.create_radio_button("Random")
        self.radio_group.addButton(self.radio_random)
        top_controls_layout.addWidget(self.radio_random)
        self.radio_time = self.create_radio_button("Time")
        self.radio_group.addButton(self.radio_time)
        top_controls_layout.addWidget(self.radio_time)
        self.radio_alpha = self.create_radio_button("Alphabetical")
        self.radio_group.addButton(self.radio_alpha)
        top_controls_layout.addWidget(self.radio_alpha)

        # Add sort direction radio buttons
        top_controls_layout.addSpacing(20) # Add some space
        self.direction_group = QButtonGroup(self)
        self.direction_group.buttonToggled.connect(self.on_sort_direction_changed)

        self.radio_asc = self.create_radio_button("Ascending")
        self.direction_group.addButton(self.radio_asc)
        top_controls_layout.addWidget(self.radio_asc)

        self.radio_desc = self.create_radio_button("Descending")
        self.direction_group.addButton(self.radio_desc)
        top_controls_layout.addWidget(self.radio_desc)

        top_controls_layout.addStretch()
        container_layout.addLayout(top_controls_layout)

        self.main_content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        container_layout.addWidget(self.main_content_splitter, 1)

        # --- File Tree View (Left Side) ---
        tree_view_container = QVBoxLayout()
        tree_view_container.setContentsMargins(0,0,0,0)
        tree_view_container.setSpacing(5)

        self.file_system_model = QFileSystemModel()
        self.file_system_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self.file_system_model.setNameFilterDisables(False)
        self.tree_view = QTreeView(self)
        self.tree_view.setModel(self.file_system_model)
        self.tree_view.setHeaderHidden(True)
        for i in range(1, 4): self.tree_view.hideColumn(i)
        self.tree_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree_view.clicked.connect(self.on_tree_view_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.open_tree_view_context_menu)
        self.tree_view.setStyleSheet(
            "QTreeView { background-color: #282828; color: white; border-radius: 5px; }"
            "QTreeView::item:selected { background-color: #55aaff; color: black; }"
        )
        tree_view_container.addWidget(self.tree_view)

        tree_view_widget = QWidget()
        tree_view_widget.setLayout(tree_view_container)
        self.main_content_splitter.addWidget(tree_view_widget)

        self.image_info_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_content_splitter.addWidget(self.image_info_splitter)

        self.image_label = ImageLabel(self)
        self.image_info_splitter.addWidget(self.image_label)

        self.info_pane_widget = QWidget()
        info_pane_layout = QVBoxLayout(self.info_pane_widget)
        info_pane_layout.setContentsMargins(0, 0, 0, 0)
        info_pane_layout.setSpacing(5)

        self.info_search_bar = QLineEdit()
        self.info_search_bar.setPlaceholderText("Search in PNG info (space-separated)...")
        self.info_search_bar.setStyleSheet("QLineEdit { background-color: #282828; color: white; border: 1px solid #555; border-radius: 3px; padding: 5px; } QMenu { background-color: #333; color: white; } QMenu::item:selected { background-color: #55aaff; }")
        self.info_search_bar.textChanged.connect(self.highlight_info_text)
        info_pane_layout.addWidget(self.info_search_bar)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #333; border-radius: 5px; padding: 5px; font-family: 'Courier New';")
        info_pane_layout.addWidget(self.info_text)

        self.info_pane_widget.hide()
        self.image_info_splitter.addWidget(self.info_pane_widget)
        
        self.image_info_splitter.setSizes([700, 300])
        self.main_content_splitter.setSizes([200, 800])

        bottom_layout = QHBoxLayout()
        self.delete_button = self.create_button("🗑", self.delete_current_image, "Delete (Del)")
        self.prev_button = self.create_button("⏮", self.show_previous_image, "Previous (Left Arrow)")
        self.pause_button = self.create_button("⏸", self.toggle_pause, "Pause/Resume (P)")
        self.next_button = self.create_button("⏭", lambda: self.show_next_image(manual=True), "Next (Right Arrow)")
        self.counter_label = QLabel("0 / 0", self)
        self.counter_label.setStyleSheet("color: white; padding: 0 10px;")
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.prev_button)
        bottom_layout.addWidget(self.pause_button)
        bottom_layout.addWidget(self.next_button)
        bottom_layout.addWidget(self.counter_label)
        bottom_layout.addWidget(self.delete_button)
        bottom_layout.addStretch()
        container_layout.addLayout(bottom_layout)

        self.feedback_label = QLabel(self)
        self.feedback_label.setStyleSheet("color: white; font-weight: bold; background-color: rgba(0,0,0,0.7); border-radius: 5px; padding: 8px;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setParent(self)
        self.feedback_label.hide()
        
        self.size_grip = QSizeGrip(self)

    def create_button(self, text, on_click, tooltip):
        button = QPushButton(text, self)
        button.setStyleSheet(
            "QPushButton { background-color: transparent; color: white; border: none; font-size: 20px; padding: 5px; }"
            "QPushButton:hover { color: #55aaff; }"
            "QPushButton:pressed { color: #3388cc; }"
            "QPushButton:disabled { color: #555555; }"
        )
        button.setFixedSize(35, 35)
        if on_click: button.clicked.connect(on_click)
        button.setToolTip(tooltip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def create_radio_button(self, text):
        radio = QRadioButton(text, self)
        radio.setStyleSheet("color: white;")
        radio.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return radio

    def load_settings(self):
        if not os.path.exists(self.CONFIG_FILE): return
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                settings = json.load(f)
                self.source_folder = settings.get('source')
                self.favorites_folder = settings.get('favorites')
                self.likes_folder = settings.get('likes')
                self.current_sort_order = settings.get('sort_order', "random")
                self.slideshow_interval = settings.get('interval', 5000)
                self.confirm_delete = settings.get('confirm_delete', True)
                self.skip_non_matching = settings.get('skip_non_matching', False)
                self.info_panel_visible = settings.get('info_panel_visible', False)
                self.current_sort_direction = settings.get('sort_direction', "asc") # Load sort direction

                if self.current_sort_order == "time": self.radio_time.setChecked(True)
                elif self.current_sort_order == "alpha": self.radio_alpha.setChecked(True)
                else: self.radio_random.setChecked(True)

                if self.current_sort_direction == "desc": self.radio_desc.setChecked(True) # Set direction radio button
                else: self.radio_asc.setChecked(True)

                if self.info_panel_visible:
                    self.info_pane_widget.show()

        except (json.JSONDecodeError, KeyError): self.clear_settings()
        finally: self.update_button_states()

    def save_settings(self):
        settings = {
            'source': self.source_folder, 'favorites': self.favorites_folder, 'likes': self.likes_folder, 
            'sort_order': self.current_sort_order, 'interval': self.slideshow_interval, 
            'confirm_delete': self.confirm_delete, 'skip_non_matching': self.skip_non_matching,
            'info_panel_visible': self.info_panel_visible, 'sort_direction': self.current_sort_direction # Save sort direction
        }
        with open(self.CONFIG_FILE, 'w') as f: json.dump(settings, f, indent=4)

    def clear_settings(self):
        self.source_folder = self.favorites_folder = self.likes_folder = None
        if os.path.exists(self.CONFIG_FILE): os.remove(self.CONFIG_FILE)
        self.update_button_states()

    def open_settings_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #333; color: white; } QMenu::item:selected { background-color: #55aaff; }")
        menu.addAction(QAction("Change Source Folder", self, triggered=lambda: self.prompt_for_folder('source')))
        menu.addAction(QAction("Change Favorites Folder", self, triggered=lambda: self.prompt_for_folder('favorites')))
        menu.addAction(QAction("Change Likes Folder", self, triggered=lambda: self.prompt_for_folder('likes')))
        menu.addSeparator()
        menu.addAction(QAction(f"Set Interval ({self.slideshow_interval/1000:.1f}s)...", self, triggered=self.set_interval))
        
        confirm_action = QAction("Confirm Before Deleting", self, checkable=True)
        confirm_action.setChecked(self.confirm_delete)
        confirm_action.triggered.connect(self.toggle_confirm_delete)
        menu.addAction(confirm_action)

        skip_action = QAction("Skip to matching image", self, checkable=True)
        skip_action.setChecked(self.skip_non_matching)
        skip_action.triggered.connect(self.toggle_skip_non_matching)
        menu.addAction(skip_action)
        menu.addSeparator()
        menu.addAction(QAction("About Slidescovery", self, triggered=self.show_about_dialog))

        menu.exec(self.title_bar.settings_button.mapToGlobal(QPoint(0, self.title_bar.settings_button.height())))

    def set_interval(self):
        new_interval, ok = QInputDialog.getDouble(self, "Set Interval", "Enter interval in seconds (0.5-60):", self.slideshow_interval / 1000, 0.5, 60, 1)
        if ok:
            self.slideshow_interval = int(new_interval * 1000)
            self.save_settings()
            if not self.is_paused: self.timer.start(self.slideshow_interval)
            self.show_feedback(f"Interval set to {new_interval}s")

    def toggle_confirm_delete(self, checked):
        self.confirm_delete = checked
        self.save_settings()
        self.show_feedback(f"Deletion confirmation {'enabled' if checked else 'disabled'}")

    def toggle_skip_non_matching(self, checked):
        self.skip_non_matching = checked
        self.save_settings()
        self.show_feedback(f"Skip to match is now {'ON' if checked else 'OFF'}")
        if not checked:
            self.is_skipping = False # Cancel any ongoing search

    def prompt_for_folder(self, folder_type):
        title_map = {'source': "Select Image Source Folder", 'favorites': "Select Favorites Folder", 'likes': "Select Likes Folder"}
        folder_path = QFileDialog.getExistingDirectory(self, title_map[folder_type])
        if not folder_path: return
        setattr(self, f"{folder_type}_folder", folder_path)
        self.save_settings()
        self.update_button_states()
        if folder_type == 'source': 
            self._set_tree_view_root() # Call helper to set up tree view
            self.load_images(folder_path)
            self.apply_sorting()
            self.current_index = 0
            self.start_slideshow()

    def update_button_states(self):
        self.title_bar.fav_button.setEnabled(bool(self.favorites_folder))
        self.title_bar.like_button.setEnabled(bool(self.likes_folder))

    def on_tree_view_clicked(self, index):
        selected_path = self.file_system_model.filePath(index)
        if os.path.isdir(selected_path):
            self.load_images(selected_path)
            self.apply_sorting()
            self.current_index = 0
            self.start_slideshow()
            
            # Ensure the path from the source folder to the selected folder is expanded
            # and the selected folder is highlighted.
            # The root of the tree view remains fixed at the source_folder's parent.
            self.tree_view.setCurrentIndex(index) # Highlight the clicked folder
            self.tree_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter) # Scroll to it

    def open_tree_view_context_menu(self, position):
        index = self.tree_view.indexAt(position)
        if not index.isValid(): return
        selected_path = self.file_system_model.filePath(index)
        if not os.path.isdir(selected_path): return
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #333; color: white; } QMenu::item:selected { background-color: #55aaff; }")
        open_action = QAction("Open in Explorer", self, triggered=lambda: os.startfile(selected_path))
        menu.addAction(open_action)
        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def load_images(self, folder_path):
        valid_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        try:
            self.image_files = [os.path.normpath(os.path.join(folder_path, f)) for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in valid_extensions]
        except FileNotFoundError: 
            self.show_feedback(f"Source folder not found.", 5000)
            self.clear_settings()
            return
        if not self.image_files: self.image_label.setText("No images found in source folder.")
        self.update_counter()

    def on_sort_order_changed(self, button, checked):
        if checked:
            if button == self.radio_random: self.current_sort_order = "random"
            elif button == self.radio_time: self.current_sort_order = "time"
            elif button == self.radio_alpha: self.current_sort_order = "alpha"
            self.apply_sorting()
            self.current_index = 0
            self.display_current_image()
            self.save_settings()

    def on_sort_direction_changed(self, button, checked):
        if checked:
            if button == self.radio_asc: self.current_sort_direction = "asc"
            elif button == self.radio_desc: self.current_sort_direction = "desc"
            self.apply_sorting()
            self.current_index = 0
            self.display_current_image()
            self.save_settings()

    def apply_sorting(self):
        if not self.image_files: return
        if self.current_sort_order == "random": random.shuffle(self.image_files)
        elif self.current_sort_order == "time": 
            self.image_files.sort(key=os.path.getctime, reverse=(self.current_sort_direction == "desc"))
        elif self.current_sort_order == "alpha": 
            self.image_files.sort(key=lambda x: os.path.basename(x).lower(), reverse=(self.current_sort_direction == "desc"))

    def start_slideshow(self):
        self.display_current_image()
        if not self.is_paused: self.timer.start(self.slideshow_interval)

    def show_random_image(self):
        if not self.image_files: return
        if len(self.image_files) > 1:
            # Select a random index different from the current one, if possible
            new_index = random.randrange(len(self.image_files))
            while new_index == self.current_index and len(self.image_files) > 1:
                new_index = random.randrange(len(self.image_files))
            self.current_index = new_index
        else:
            self.current_index = 0 # Only one image, just show it

        self.display_current_image()
        if not self.is_paused: self.timer.start(self.slideshow_interval)

    def display_current_image(self):
        if self.is_skipping or not self.image_files: return
        image_path = self.image_files[self.current_index]
        self.current_pixmap = QPixmap(image_path)
        if self.current_pixmap.isNull(): self.handle_load_error(); return
        self.update_image_display()
        self.load_png_info(image_path)
        self.update_counter()

    def update_counter(self):
        if self.image_files: self.counter_label.setText(f"{self.current_index + 1} / {len(self.image_files)}")
        else: self.counter_label.setText("0 / 0")

    def load_png_info(self, image_path):
        self.info_text.clear()
        if image_path.lower().endswith('.png'):
            try:
                with Image.open(image_path) as img:
                    if img.info:
                        info_items = [f"{key}:\n{value}" for key, value in img.info.items()]
                        info_text = "\n\n".join(info_items)
                        self.info_text.setPlainText(info_text)
            except Exception: pass
        self.highlight_info_text()

    def highlight_info_text(self):
        search_text = self.info_search_bar.text()
        search_terms = [term for term in re.split(r'[\s　]+', search_text) if term]
        document = self.info_text.document()
        
        cursor = QTextCursor(document)
        cursor.select(QTextCursor.SelectionType.Document)
        default_format = QTextCharFormat()
        cursor.setCharFormat(default_format)

        if not search_terms: return

        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor("#FFC107"))
        highlight_format.setForeground(QColor("black"))

        for term in search_terms:
            cursor = QTextCursor(document)
            while not cursor.isNull() and not cursor.atEnd():
                cursor = document.find(term, cursor)
                if not cursor.isNull():
                    cursor.mergeCharFormat(highlight_format)
                else:
                    break

    def handle_load_error(self):
        self.image_files.pop(self.current_index)
        if not self.image_files: self.close(); return
        if self.current_index >= len(self.image_files): self.current_index = 0
        self.display_current_image()

    def show_next_image(self, manual=False):
        self.is_skipping = False # Stop any current skip
        if not self.image_files or (not manual and self.is_paused):
            return
        
        if manual and not self.is_paused:
            self.timer.start(self.slideshow_interval)

        if self.skip_non_matching and self.info_search_bar.text():
            self.is_skipping = True
            self.show_feedback("Searching for next match...", position='bottom')
            self.find_match(direction=1, start_index=self.current_index)
        else:
            self.current_index = (self.current_index + 1) % len(self.image_files)
            self.display_current_image()

    def show_previous_image(self):
        self.is_skipping = False # Stop any current skip
        if not self.image_files:
            return

        if not self.is_paused:
            self.timer.start(self.slideshow_interval)

        if self.skip_non_matching and self.info_search_bar.text():
            self.is_skipping = True
            self.show_feedback("Searching for previous match...", position='bottom')
            self.find_match(direction=-1, start_index=self.current_index)
        else:
            self.current_index = (self.current_index - 1 + len(self.image_files)) % len(self.image_files)
            self.display_current_image()

    def get_png_info_text(self, image_path):
        info_content = ""
        if image_path.lower().endswith('.png'):
            try:
                with Image.open(image_path) as img:
                    if img.info:
                        info_items = [f"{key}:\n{value}" for key, value in img.info.items()]
                        info_content = "\n\n".join(info_items)
            except Exception:
                pass
        return info_content

    def find_match(self, direction, start_index):
        if not self.is_skipping:
            return

        self.current_index = (self.current_index + direction + len(self.image_files)) % len(self.image_files)

        if self.current_index == start_index:
            self.is_skipping = False
            self.show_feedback("No more matches found.", position='bottom')
            self.display_current_image()
            return

        image_path = self.image_files[self.current_index]
        info_content = self.get_png_info_text(image_path).lower()
        search_text = self.info_search_bar.text()
        search_terms = [term.lower() for term in re.split(r'[\s　]+', search_text) if term]

        is_match = all(term in info_content for term in search_terms)

        if search_terms and is_match:
            self.is_skipping = False
            self.show_feedback("Match found!", position='bottom')
            self.display_current_image()
            if not self.is_paused:
                self.timer.start(self.slideshow_interval)
        else:
            QTimer.singleShot(10, lambda: self.find_match(direction, start_index))

    def delete_current_image(self):
        if not self.image_files: return
        path_to_delete = self.image_files[self.current_index]
        if self.confirm_delete:
            reply = QMessageBox.question(self, 'Confirm Delete',
                                         f"Are you sure you want to move this file to the trash?\n\n{os.path.basename(path_to_delete)}",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No: return

        if not os.path.exists(path_to_delete): 
            self.show_feedback(f"File not found. Removing from list.")
            self.handle_load_error()
            return
        try:
            send2trash.send2trash(path_to_delete)
            self.image_files.pop(self.current_index)
            if not self.image_files: 
                self.image_label.setText("No more images.")
                self.update_counter()
                QTimer.singleShot(2000, self.close)
                return
            if self.current_index >= len(self.image_files): self.current_index = 0
            self.display_current_image()
            self.show_feedback("Moved to Trash")
        except Exception as e: self.show_feedback(f"Error: {e}")

    def copy_image(self, dest_folder, name):
        if not dest_folder: self.show_feedback(f"'{name}' folder not set"); return
        if not self.image_files: return
        source_path = self.image_files[self.current_index]
        dest_path = os.path.join(dest_folder, os.path.basename(source_path))
        try: 
            shutil.copy2(source_path, dest_path)
            self.show_feedback(f"Copied to {name}!")
        except Exception as e: self.show_feedback(f"Error: {e}")

    def add_to_favorites(self): self.copy_image(self.favorites_folder, "Favorites")
    def add_to_likes(self): self.copy_image(self.likes_folder, "Likes")

    def show_feedback(self, message, duration=2000, position='center'):
        self.feedback_position = position
        self.feedback_label.setText(message)
        self.feedback_label.adjustSize()
        self.feedback_label.show()
        self.reposition_feedback()
        QTimer.singleShot(duration, self.feedback_label.hide)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.pause_button.setText("▶" if self.is_paused else "⏸")
        if self.is_paused: 
            self.timer.stop()
            self.is_skipping = False
            self.show_feedback("Paused")
        else: 
            self.timer.start(self.slideshow_interval)
            self.show_feedback("Resumed")

    def toggle_info_pane(self):
        if self.info_pane_widget.isVisible():
            self.info_pane_widget.hide()
            self.info_panel_visible = False
            self.setFocus()
        else:
            self.info_pane_widget.show()
            self.info_panel_visible = True
            self.info_search_bar.setFocus()
        self.save_settings()

    def toggle_tree_view(self):
        if self.tree_view.isVisible():
            self.tree_view.hide()
            self.tree_toggle_button.setText(">>")
        else:
            self.tree_view.show()
            self.tree_toggle_button.setText("<<")

    def update_image_display(self):
        if self.current_pixmap and not self.current_pixmap.isNull():
            scaled_pixmap = self.current_pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.reposition_feedback()
        self.size_grip.move(self.rect().right() - self.size_grip.width(), self.rect().bottom() - self.size_grip.height())
        self.size_grip.raise_()

    def reposition_feedback(self):
        if not self.feedback_label.isVisible():
            return

        if self.feedback_position == 'bottom':
            x = (self.width() - self.feedback_label.width()) / 2
            y = self.height() - self.feedback_label.height() - 45
        else: # Default to center
            x = (self.width() - self.feedback_label.width()) / 2
            y = (self.height() - self.feedback_label.height()) / 2

        self.feedback_label.move(int(x), int(y))
        self.feedback_label.raise_()

    def toggle_maximize_restore(self):
        if self.isMaximized():
            self.showNormal()
            self.title_bar.maximize_restore_button.setText("🗗")
        else:
            self.showMaximized()
            self.title_bar.maximize_restore_button.setText("🗗")

    def keyPressEvent(self, event: QKeyEvent):
        if self.info_search_bar.hasFocus():
            super().keyPressEvent(event)
            return
            
        if not self.image_files: return
        key_map = {
            Qt.Key.Key_Right: lambda: self.show_next_image(manual=True), Qt.Key.Key_Left: self.show_previous_image, 
            Qt.Key.Key_Up: self.show_random_image, Qt.Key.Key_Down: self.show_random_image,
            Qt.Key.Key_1: self.add_to_favorites, Qt.Key.Key_2: self.add_to_likes, 
            Qt.Key.Key_P: self.toggle_pause, Qt.Key.Key_I: self.toggle_info_pane,
            Qt.Key.Key_Delete: self.delete_current_image, Qt.Key.Key_Escape: self.close
        }
        action = key_map.get(event.key())
        if action: action()

    def wheelEvent(self, event: QWheelEvent):
        if self.info_pane_widget.isVisible() and self.info_pane_widget.underMouse():
            return

        if not self.image_files: return
        if event.angleDelta().y() > 0: self.show_previous_image()
        else: self.show_next_image(manual=True)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.old_pos = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path) and file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                self.load_single_image(file_path)
                event.acceptProposedAction()
                return
        event.ignore()

    def load_single_image(self, image_path):
        self.is_skipping = False
        folder_path = os.path.dirname(image_path)
        self.source_folder = folder_path
        self.save_settings()
        self._set_tree_view_root() # Call helper to set up tree view
        self.load_images(folder_path)
        self.apply_sorting()
        
        normalized_dropped_image_path = os.path.normpath(image_path)
        try: self.current_index = self.image_files.index(normalized_dropped_image_path)
        except ValueError: self.current_index = 0
            
        self.display_current_image()
        self.timer.stop()
        self.is_paused = True
        self.pause_button.setText("▶")

    def _set_tree_view_root(self):
        if self.source_folder and os.path.exists(self.source_folder):
            # Set the model's root to the parent of the source_folder
            # This allows the source_folder itself to be an item in the tree
            parent_dir = os.path.dirname(self.source_folder)
            if not parent_dir: # Handle case where source_folder is a drive root (e.g., C:\)
                parent_dir = self.source_folder # If it's a drive root, treat it as its own parent for display purposes

            self.file_system_model.setRootPath(parent_dir)

            # Set the tree view's visible root to the parent directory
            self.tree_view.setRootIndex(self.file_system_model.index(parent_dir))

            # Expand and select the source folder itself
            source_index = self.file_system_model.index(self.source_folder)
            self.tree_view.expand(source_index)
            self.tree_view.setCurrentIndex(source_index)

    def show_about_dialog(self):
        about_text = """
        Slidescovery
        Version 1.0

        This application is licensed under the GNU General Public License v3 (GPLv3).
        The source code is available at: https://github.com/jogetu/slidescovery

        This application uses the following third-party libraries:

        - PyQt6
          Licensed under the GPLv3.
          Copyright © 2023 Riverbank Computing Limited.
          Source: https://www.riverbankcomputing.com/software/pyqt/

        - Pillow
          Licensed under the HPND License.
          Copyright © 2010-2023 Alex Clark and contributors.

        - send2trash
          Licensed under the BSD License.
          Copyright © 2017, Hameedullah Khan
          Copyright © 2012, Arseniy Krasnov
          Copyright © 2009, 2010, Hardcoded Software

        Please see the LICENSE.txt file for full license details.
        """
        QMessageBox.about(self, "About Slidescovery", about_text)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(script_dir, "favicon.ico")
    app.setWindowIcon(QIcon(icon_path))
    widget = SlideshowWidget()
    widget.show()
    sys.exit(app.exec())
