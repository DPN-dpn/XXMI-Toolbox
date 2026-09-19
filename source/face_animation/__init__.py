import bpy

from . import properties
from . import operators
from . import panel

modules = [
    properties,
    operators,
    panel,
]

def register():
    for mod in modules:
        mod.register()

def unregister():
    for mod in reversed(modules):
        mod.unregister()
