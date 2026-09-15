import bpy
from . import updator
from . import convert_shadow
from . import copy_metadata
from . import separate_by_vertex_group

class XXMI_OT_help_tooltip(bpy.types.Operator):
    bl_idname = "object.xxmi_help_tooltip"
    bl_label = "도움말"
    
    text: bpy.props.StringProperty()
    
    @classmethod
    def description(cls, context, properties):
        return properties.text if properties else ""
        
    def execute(self, context):
        return {'FINISHED'}

modules = [
    updator,
    convert_shadow,
    copy_metadata,
    separate_by_vertex_group,
]

def register():
    bpy.utils.register_class(XXMI_OT_help_tooltip)
    for mod in modules:
        if hasattr(mod, "register"):
            mod.register()

def unregister():
    for mod in reversed(modules):
        if hasattr(mod, "unregister"):
            mod.unregister()
    bpy.utils.unregister_class(XXMI_OT_help_tooltip)