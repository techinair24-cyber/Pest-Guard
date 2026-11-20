import inspect


def pytest_configure():
    # Older Keras rejects newer serializer output for default axis values.
    from keras.initializers import GlorotUniform

    initializer_parameters = inspect.signature(
        GlorotUniform.__init__
    ).parameters
    unsupported_axes = {
        name
        for name in ("input_axes", "output_axes")
        if name not in initializer_parameters
    }
    if not unsupported_axes:
        return

    original_init = GlorotUniform.__init__

    def compatible_init(self, *args, **kwargs):
        for name in unsupported_axes:
            if name in kwargs:
                value = kwargs.pop(name)
                if value is not None:
                    raise TypeError(
                        f"Test compatibility shim cannot ignore non-default {name}"
                    )
        original_init(self, *args, **kwargs)

    GlorotUniform.__init__ = compatible_init
