from copy import deepcopy
from pathlib import Path
import tempfile
import threading

from PySide6.QtCore import Qt, QUrl, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
    QPushButton, QSlider, QLabel, QFormLayout, QDoubleSpinBox, QMessageBox,
    QFileDialog, QProgressBar, QComboBox)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget

from .model import Clip, save_project, load_project
from .render import probe, render, Cancelled


class TimelineList(QListWidget):
    """Timeline list whose internal drag moves update the owning Window.

    QListWidget implements InternalMove drops as remove+insert, so the model
    only emits rowsRemoved/rowsInserted - never rowsMoved. Relying on
    rowsMoved silently dropped clip reordering, so drops are handled here.
    """

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setMaximumHeight(120)

    def dropEvent(self, event):
        super().dropEvent(event)
        # InternalMove drops land here only when super() accepted them; any
        # foreign or invalid drop stays unaccepted and must not rebuild the
        # clip list.
        if event.isAccepted() and event.proposedAction() == Qt.DropAction.MoveAction:
            self._window.reordered()


class RenderJob(QThread):
    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, clips, output, size):
        super().__init__()
        self.clips, self.output, self.size = deepcopy(clips), output, size
        self.cancel = threading.Event()

    def run(self):
        try:
            render(self.clips, self.output, *self.size,
                   progress=lambda v: self.progress.emit(round(v*100)), cancel=self.cancel)
            self.succeeded.emit(self.output)
        except Cancelled:
            self.failed.emit('Render cancelled.')
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Creative Studio')
        self.resize(1280, 800)
        self.clips, self.history, self.future = [], [], []
        self.project_path = None
        self.dirty = False
        self.preview_ready = False
        self.job = None
        self.closing = False
        self.temp = tempfile.TemporaryDirectory(prefix='creative-studio-preview-')
        self.preview_path = str(Path(self.temp.name) / 'preview.mp4')
        self.player = QMediaPlayer(self)
        # Do not create an audio output when Qt reports no device.
        self.audio = None
        if QMediaDevices.audioOutputs():
            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.8)
            self.player.setAudioOutput(self.audio)
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.controls = QWidget(); top = QHBoxLayout(self.controls)
        for title, action in [('Import', self.import_media), ('Split (S)', self.split_clip),
                              ('Delete', self.delete_clip), ('Render preview', self.preview),
                              ('Export MP4', self.export)]:
            button = QPushButton(title); button.clicked.connect(action); top.addWidget(button)
        self.resolution = QComboBox()
        self.resolution.addItems(['1920 × 1080', '1280 × 720', '1080 × 1920'])
        top.addWidget(self.resolution)
        layout.addWidget(self.controls)
        splitter = QSplitter(); layout.addWidget(splitter, 1)
        self.media = QListWidget()
        self.media.itemDoubleClicked.connect(self.add_media)
        self.media.setMinimumWidth(200)
        pane = QWidget(); pl = QVBoxLayout(pane)
        pl.addWidget(QLabel('PROJECT MEDIA · Double-click to append'))
        pl.addWidget(self.media); splitter.addWidget(pane)
        center = QWidget(); cl = QVBoxLayout(center)
        self.video = QVideoWidget(); self.video.setMinimumSize(400, 240)
        self.player.setVideoOutput(self.video); cl.addWidget(self.video, 1)
        self.preview_label = QLabel('Render preview after editing to see the full timeline.')
        cl.addWidget(self.preview_label)
        transport = QHBoxLayout()
        play = QPushButton('Play / Pause'); play.clicked.connect(self.play)
        transport.addWidget(play)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0); self.seek.sliderMoved.connect(self.player.setPosition)
        transport.addWidget(self.seek, 1)
        self.time = QLabel('0.00 / 0.00 s'); transport.addWidget(self.time)
        cl.addLayout(transport); splitter.addWidget(center)
        self.inspector = QWidget(); form = QFormLayout(self.inspector)
        form.addRow(QLabel('CLIP INSPECTOR'))
        self.fields = {}
        for key, label, low, high, default in [
            ('start', 'In (seconds)', 0, 999999, 0),
            ('end', 'Out (seconds)', 0, 999999, 1),
            ('speed', 'Speed', 0.125, 8, 1),
            ('fade_in', 'Fade in (seconds)', 0, 999999, 0),
            ('fade_out', 'Fade out (seconds)', 0, 999999, 0),
            ('brightness', 'Brightness', -1, 1, 0),
            ('contrast', 'Contrast', 0, 3, 1),
            ('saturation', 'Saturation', 0, 3, 1),
            ('volume', 'Volume', 0, 4, 1)]:
            spin = QDoubleSpinBox(); spin.setRange(low, high)
            spin.setDecimals(3); spin.setSingleStep(0.1); spin.setValue(default)
            self.fields[key] = spin; form.addRow(label, spin)
        apply_button = QPushButton('Apply to selected clip')
        apply_button.clicked.connect(self.apply_clip); form.addRow(apply_button)
        splitter.addWidget(self.inspector); splitter.setSizes([220, 780, 280])
        layout.addWidget(QLabel('TIMELINE · Drag to reorder · Splits use the rendered preview playhead'))
        self.timeline = TimelineList(self)
        self.timeline.currentRowChanged.connect(self.select_clip)
        layout.addWidget(self.timeline)
        footer = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setRange(0, 100)
        footer.addWidget(self.progress)
        self.cancel_button = QPushButton('Cancel render')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self.job.cancel.set() if self.job else None)
        footer.addWidget(self.cancel_button); layout.addLayout(footer)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.errorOccurred.connect(lambda *_: self.statusBar().showMessage(self.player.errorString()))
        self.actions = []
        for name, shortcut, handler in [('New', 'Ctrl+N', self.new_project),
             ('Open', 'Ctrl+O', self.open_project), ('Save', 'Ctrl+S', self.save),
             ('Save as', 'Ctrl+Shift+S', lambda: self.save(True)),
             ('Import media', 'Ctrl+I', self.import_media), ('Split clip', 'S', self.split_clip),
             ('Delete clip', 'Delete', self.delete_clip), ('Undo', 'Ctrl+Z', self.undo),
             ('Redo', 'Ctrl+Shift+Z', self.redo), ('Export', 'Ctrl+E', self.export)]:
            act = QAction(name, self); act.setShortcut(shortcut)
            act.triggered.connect(handler); self.actions.append(act)
        file_menu = self.menuBar().addMenu('File')
        for act in self.actions: file_menu.addAction(act)
        self.setStyleSheet('''QWidget {background:#202329; color:#e8eaf0; font-size:13px;}
            QListWidget,QDoubleSpinBox,QComboBox {background:#16191e; border:1px solid #414650;}
            QPushButton {background:#353b48; padding:8px; border-radius:4px;}
            QPushButton:hover {background:#4b5670;}
            QListWidget::item:selected {background:#485aa6;}
            QProgressBar::chunk {background:#6687ef;}''')
        self.statusBar().showMessage('Ready' if self.audio else 'Ready · No audio device: silent preview')

    def error(self, exc):
        QMessageBox.warning(self, 'Creative Studio', str(exc))

    def remember(self):
        self.history.append(deepcopy(self.clips)); self.history = self.history[-50:]
        self.future.clear()

    def changed(self):
        self.dirty = True; self.preview_ready = False
        self.player.stop(); self.player.setSource(QUrl())
        self.preview_label.setText('Preview out of date · Click Render preview')
        name = Path(self.project_path).name if self.project_path else None
        base = f'Creative Studio · {name}' if name else 'Creative Studio'
        self.setWindowTitle(f'{base} *')

    def refresh(self, selected=0):
        self.timeline.clear()
        for clip in self.clips:
            item = QListWidgetItem(f'{Path(clip.path).name}\n{clip.duration:.2f}s · {clip.speed:g}×')
            item.setData(Qt.ItemDataRole.UserRole, clip)
            self.timeline.addItem(item)
        if self.clips:
            self.timeline.setCurrentRow(min(max(0, selected), len(self.clips)-1))

    def select_clip(self, row):
        if 0 <= row < len(self.clips):
            for key, field in self.fields.items():
                field.setValue(getattr(self.clips[row], key))

    def reordered(self, *_):
        self.remember()
        self.clips = [self.timeline.item(i).data(Qt.ItemDataRole.UserRole)
                      for i in range(self.timeline.count())]
        self.changed(); self.select_clip(self.timeline.currentRow())

    def import_media(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Import videos', '',
                         'Video files (*.mp4 *.mov *.mkv *.webm *.avi *.m4v);;All files (*)')
        errors = []
        added = False
        for path in paths:
            try:
                duration, _ = probe(path)
                if not added: self.remember(); added = True
                clip = Clip(str(Path(path).resolve()), 0, duration)
                self.clips.append(clip)
                item = QListWidgetItem(Path(path).name)
                item.setData(Qt.ItemDataRole.UserRole, (clip.path, duration))
                self.media.addItem(item)
            except Exception as exc:
                errors.append(f'{Path(path).name}: {exc}')
        if added: self.changed(); self.refresh(len(self.clips)-1)
        if errors: self.error('\n'.join(errors))

    def add_media(self, item):
        path, duration = item.data(Qt.ItemDataRole.UserRole)
        self.remember(); self.clips.append(Clip(path, 0, duration))
        self.changed(); self.refresh(len(self.clips)-1)

    def apply_clip(self):
        row = self.timeline.currentRow()
        if row < 0: return
        try:
            clip = Clip(self.clips[row].path, **{k: f.value() for k, f in self.fields.items()})
            clip.validate()
            duration, _ = probe(clip.path)
            if clip.end > duration + 0.05: raise ValueError('Out point exceeds source duration.')
            self.remember(); self.clips[row] = clip; self.changed(); self.refresh(row)
        except Exception as exc: self.error(exc)

    def delete_clip(self):
        row = self.timeline.currentRow()
        if row >= 0:
            self.remember(); del self.clips[row]; self.changed(); self.refresh(row)

    def split_clip(self):
        if not self.preview_ready:
            self.error('Render preview first, then seek to the split position.'); return
        seconds = self.player.position()/1000
        offset = 0.0
        for i, clip in enumerate(self.clips):
            if offset <= seconds < offset+clip.duration:
                try:
                    a, b = clip.split(seconds-offset)
                    self.remember(); self.clips[i:i+1] = [a, b]
                    self.changed(); self.refresh(i)
                except Exception as exc: self.error(exc)
                return
            offset += clip.duration

    def undo(self):
        if self.history:
            self.future.append(deepcopy(self.clips)); self.clips = self.history.pop()
            self.changed(); self.refresh()

    def redo(self):
        if self.future:
            self.history.append(deepcopy(self.clips)); self.clips = self.future.pop()
            self.changed(); self.refresh()

    def position_changed(self, position):
        if not self.seek.isSliderDown(): self.seek.setValue(position)
        self.time.setText(f'{position/1000:.2f} / {self.player.duration()/1000:.2f} s')

    def play(self):
        if not self.preview_ready: return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else: self.player.play()

    def preview(self):
        self.player.stop(); self.player.setSource(QUrl())
        self.start_render(self.preview_path, (640, 360, 30), True)

    def export(self):
        if not self.clips: self.error('Import a video first.'); return
        path, _ = QFileDialog.getSaveFileName(self, 'Export MP4', 'creative-studio.mp4', 'MP4 (*.mp4)')
        if path:
            if not path.lower().endswith('.mp4'): path += '.mp4'
            if Path(path).exists() and QMessageBox.question(self, 'Replace output?',
               f'Replace {path}?') != QMessageBox.StandardButton.Yes: return
            size = [(1920,1080,30), (1280,720,30), (1080,1920,30)][self.resolution.currentIndex()]
            self.start_render(path, size, False)

    def start_render(self, path, size, preview):
        if self.job: return
        if not self.clips: self.error('Import a video first.'); return
        self.progress.setValue(0)
        self.controls.setEnabled(False); self.inspector.setEnabled(False)
        self.timeline.setEnabled(False); self.media.setEnabled(False)
        for action in self.actions: action.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.job = RenderJob(self.clips, path, size)
        self.job.progress.connect(self.progress.setValue)
        self.job.succeeded.connect(lambda p: self.render_done(p, preview))
        self.job.failed.connect(self.render_failed)
        self.job.finished.connect(self.render_finished)
        self.statusBar().showMessage('Rendering…')
        self.job.start()

    def render_done(self, path, preview):
        if preview:
            self.preview_ready = True
            self.player.setSource(QUrl.fromLocalFile(path))
            self.preview_label.setText('Timeline preview · Seek and press S to split')
        self.statusBar().showMessage('Preview ready' if preview else f'Exported: {path}')

    def render_failed(self, message):
        self.statusBar().showMessage(message)
        if message != 'Render cancelled.': self.error(message)

    def render_finished(self):
        self.job.deleteLater(); self.job = None
        self.controls.setEnabled(True); self.inspector.setEnabled(True)
        self.timeline.setEnabled(True); self.media.setEnabled(True)
        for action in self.actions: action.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.closing: self.close()

    def save(self, save_as=False):
        path = self.project_path
        if save_as or not path:
            path, _ = QFileDialog.getSaveFileName(self, 'Save project', 'untitled.csproj', 'Project (*.csproj)')
        if not path: return False
        if not path.endswith('.csproj'): path += '.csproj'
        try:
            save_project(path, self.clips)
            self.project_path = path; self.dirty = False
            self.setWindowTitle(f'Creative Studio · {Path(path).name}')
            return True
        except Exception as exc: self.error(exc); return False

    def confirm_discard(self):
        if not self.dirty: return True
        result = QMessageBox.question(self, 'Unsaved edits', 'Save this project before continuing?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return result == QMessageBox.StandardButton.Discard or (result == QMessageBox.StandardButton.Save and self.save())

    def new_project(self):
        if not self.confirm_discard(): return
        self.clips = []; self.history.clear(); self.future.clear()
        self.project_path = None; self.media.clear(); self.changed(); self.refresh()
        self.dirty = False; self.setWindowTitle('Creative Studio')

    def open_project(self):
        if not self.confirm_discard(): return
        path, _ = QFileDialog.getOpenFileName(self, 'Open project', '', 'Project (*.csproj)')
        if not path: return
        try:
            clips = load_project(path)
            self.clips = clips; self.history.clear(); self.future.clear()
            self.media.clear(); self.changed(); self.refresh()
            self.project_path = path; self.dirty = False
            self.setWindowTitle(f'Creative Studio · {Path(path).name}')
        except Exception as exc: self.error(exc)

    def closeEvent(self, event):
        if self.job:
            self.closing = True; self.job.cancel.set(); event.ignore(); return
        if not self.confirm_discard():
            self.closing = False; event.ignore(); return
        self.player.stop(); self.player.setSource(QUrl())
        self.temp.cleanup(); event.accept()
