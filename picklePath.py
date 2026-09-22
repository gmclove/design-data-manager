import logging
import os
import pickle


class PicklePath:
    """A generic checkpoint helper for saving and restoring Python object state.

    The helper is intentionally reusable across projects. It can:
      - save/load a checkpoint for any PicklePath-derived instance
      - recurse into nested PicklePath objects stored on attributes
      - optionally keep a log file for debugging and restart diagnostics

    The default file extension is .pkl, but older .npy checkpoints are still
    accepted for compatibility with earlier versions of this helper.
    """

    def __init__(self, dir_path=None, sub_dirs=None, file_ext='pkl', checkpoint_path=None, log_level=logging.INFO):
        if dir_path is None:
            dir_path = self.__class__.__name__

        self.abs_path = os.path.abspath(dir_path)
        self.sub_dirs = list(sub_dirs or [])
        self.file_ext = file_ext.lower().lstrip('.') or 'pkl'
        self.checkpoint_path = (
            os.path.abspath(checkpoint_path)
            if checkpoint_path
            else os.path.join(self.abs_path, f'{self.__class__.__name__}.checkpoint.{self.file_ext}')
        )
        self.log_level = log_level
        self.logger = self.get_logger()

        self.cp_init = False

        if os.path.isdir(self.abs_path):
            if os.path.exists(self.cp_path):
                self.update_self()
                self.logger.info('RESTARTED FROM CHECKPOINT')
                self.cp_init = True
                return

            legacy_path = self._legacy_cp_path()
            if legacy_path and os.path.exists(legacy_path):
                self.update_self()
                self.logger.info('RESTARTED FROM LEGACY CHECKPOINT')
                self.cp_init = True
                return
        else:
            os.makedirs(self.abs_path, exist_ok=True)
            self.logger.info(f'NEW - {self.rel_path} did not exist')

        self.load_sub_pickle_paths()

        for sub_dir in self.sub_dirs:
            sub_dir_path = os.path.join(self.abs_path, sub_dir)
            os.makedirs(sub_dir_path, exist_ok=True)

    def load_sub_pickle_paths(self):
        for attr_key, attr_val in self.__dict__.items():
            if self.is_iterable(attr_val):
                if isinstance(attr_val, dict):
                    for val in attr_val.values():
                        self.loadIfPP(val)
                else:
                    for item in attr_val:
                        self.loadIfPP(item)

            self.loadIfPP(attr_val)

    def save_sub_pickle_paths(self):
        for attr_key, attr_val in self.__dict__.items():
            if self.is_iterable(attr_val):
                if isinstance(attr_val, dict):
                    for val in attr_val.values():
                        self.saveIfPP(val)
                else:
                    for item in attr_val:
                        self.saveIfPP(item)

            self.saveIfPP(attr_val)

    def loadIfPP(self, inst):
        if self.is_pickle_path(inst):
            self.logger.info(f'LOADING: {inst} FROM {inst.cp_path}')
            inst.update_self()

    def saveIfPP(self, inst):
        if self.is_pickle_path(inst):
            self.logger.info(f'SAVING: {inst} TO {os.path.relpath(inst.cp_path)}')
            inst.save_self()

    def get_logger(self):
        name = '.'.join(os.path.normpath(self.rel_path).split(os.path.sep))
        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)

        formatter = logging.Formatter(
            '%(asctime)s :: %(levelname)-8s :: %(name)s :: %(message)s',
            '%m-%d %H:%M'
        )

        if not logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)

        self._ensure_parent_dir(self.log_path)
        if not any(
            isinstance(handler, logging.FileHandler) and getattr(handler, 'baseFilename', None) == self.log_path
            for handler in logger.handlers
        ):
            file_handler = logging.FileHandler(self.log_path)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        return logger

    def save_self(self):
        if os.path.isdir(self.abs_path):
            self.save_checkpoint(self.cp_path, self)
            self.logger.info('CHECKPOINT SAVED')
        else:
            self.logger.warning('FAILED: SAVING CHECKPOINT - directory does not exist')

        self.save_sub_pickle_paths()

    def load_self(self):
        checkpoint_path = self.cp_path

        if not os.path.exists(checkpoint_path):
            legacy_path = self._legacy_cp_path()
            if legacy_path and os.path.exists(legacy_path):
                checkpoint_path = legacy_path
            else:
                self.logger.error(f'CHECKPOINT NOT FOUND: {self.cp_path}')
                return None

        loaded_self = self.load_checkpoint(checkpoint_path)
        self.logger.info(f'\tCHECKPOINT LOADED: {self.cp_rel_path}')
        return loaded_self

    def update_self(self, loaded_self=None):
        if loaded_self is None:
            loaded_self = self.load_self()

        if loaded_self is None:
            self.logger.error('FAILED UPDATE SELF: LOADED CHECKPOINT is None')
            return

        self.__dict__.update(loaded_self.__dict__)
        self.load_sub_pickle_paths()

    def check_saves(self):
        self.logger.info(f'SAVED CHECKPOINTS CHECK - {self.cp_rel_path}')
        if os.path.exists(self.cp_path):
            loaded = self.load_checkpoint(self.cp_path)
            self.logger.info(loaded)
        else:
            self.logger.info(f'\t{self.cp_path} does not exist')

    @staticmethod
    def is_iterable(obj):
        try:
            iter(obj)
        except TypeError:
            return False
        return True

    @staticmethod
    def is_pickle_path(inst):
        if inst is None:
            return False
        if inst.__class__ is type:
            return False
        return any(base.__name__ == 'PicklePath' for base in inst.__class__.mro())

    @staticmethod
    def _normalize_checkpoint_path(path, default_ext='pkl'):
        if path is None:
            raise ValueError('A checkpoint path is required.')

        if os.path.splitext(path)[1]:
            return path

        return f'{path}.{default_ext}'

    def _legacy_cp_path(self):
        if self.file_ext == 'pkl':
            root, _ = os.path.splitext(self.cp_path)
            return root + '.npy'

        return None

    @staticmethod
    def load_checkpoint(path):
        normalized_path = PicklePath._normalize_checkpoint_path(path)

        with open(normalized_path, 'rb') as checkpoint_file:
            return pickle.load(checkpoint_file)

    @staticmethod
    def save_checkpoint(path, data):
        normalized_path = PicklePath._normalize_checkpoint_path(path)

        temp_path = normalized_path + '.tmp'
        old_path = normalized_path + '.old'

        with open(temp_path, 'wb') as checkpoint_file:
            pickle.dump(data, checkpoint_file, protocol=pickle.HIGHEST_PROTOCOL)

        if os.path.exists(normalized_path):
            os.replace(normalized_path, old_path)

        os.replace(temp_path, normalized_path)

        if os.path.exists(old_path):
            os.remove(old_path)

        return normalized_path

    @staticmethod
    def load_legacy_checkpoint(path):
        """Load a legacy .npy checkpoint created by earlier versions of this helper."""
        return PicklePath.load_checkpoint(path)

    @staticmethod
    def save_legacy_checkpoint(path, data):
        """Save a legacy .npy-compatible checkpoint while preserving the generic pickle workflow."""
        return PicklePath.save_checkpoint(path, data)

    @staticmethod
    def loadNumpyFile(path):
        """Backward-compatible alias preserved for older callers."""
        return PicklePath.load_legacy_checkpoint(path)

    @staticmethod
    def saveNumpyFile(path, data):
        """Backward-compatible alias preserved for older callers."""
        return PicklePath.save_legacy_checkpoint(path, data)

    @staticmethod
    def _ensure_parent_dir(path):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    @property
    def rel_path(self):
        return os.path.relpath(self.abs_path)

    @property
    def data_folder(self):
        _, data_folder = os.path.split(self.abs_path)
        return data_folder

    @property
    def cp_path(self):
        return self.checkpoint_path

    @property
    def cp_rel_path(self):
        return os.path.relpath(self.cp_path)

    @property
    def par_path(self):
        return os.path.dirname(self.abs_path)

    @property
    def log_path(self):
        return os.path.join(self.par_path, self.data_folder + '.log')
