from . import updator
from . import convert_shadow

modules = [
    convert_shadow,
    updator,
]

def register():
    for mod in modules:
        if hasattr(mod, "register"):
            mod.register()

def unregister():
    for mod in reversed(modules):
        if hasattr(mod, "unregister"):
            mod.unregister()