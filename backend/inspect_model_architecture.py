import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from pathlib import Path
import tensorflow as tf
from keras.initializers import GlorotUniform

path = Path("backend/ai_model/best_cnn_v3.keras")
original = GlorotUniform.from_config

@classmethod
def compatible_from_config(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)

GlorotUniform.from_config = compatible_from_config
try:
    model = tf.keras.models.load_model(path, compile=False)
finally:
    GlorotUniform.from_config = original

print("Model input:", model.input_shape)
print("Model output:", model.output_shape)
print("Total parameters:", model.count_params())
print("\nLayer summary:")
model.summary()

print("\nLayer trainability:")
for i, layer in enumerate(model.layers):
    print(
        f"{i:3} | {layer.name:35} | "
        f"{layer.__class__.__name__:20} | "
        f"trainable={layer.trainable} | "
        f"output={getattr(layer, 'output_shape', 'see summary')}"
    )
