from typing import Optional


class ModelNotConfiguredError(RuntimeError):
    pass


class PestModel:
    """Integration boundary for the trained CNN and Mel-spectrogram pipeline.

    Replace predict() with audio loading, noise handling, segmentation,
    Mel-spectrogram extraction, and CNN inference when the trained model exists.
    """

    def __init__(self):
        self.model_path: Optional[str] = None

    def predict(self, audio_file: str):
        raise ModelNotConfiguredError('AI model is not configured')


model = PestModel()
