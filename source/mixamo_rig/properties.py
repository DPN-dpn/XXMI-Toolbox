import bpy

class XXMI_PG_mixamo_rig_props(bpy.types.PropertyGroup):
    target_obj: bpy.props.PointerProperty(
        name="타겟 본",
        type=bpy.types.Object,
        description="이름을 변환할 대상 아마추어(뼈대) 오브젝트",
        poll=lambda self, object: object.type == 'ARMATURE'
    )

classes = (
    XXMI_PG_mixamo_rig_props,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.xxmi_mixamo_rig_props = bpy.props.PointerProperty(type=XXMI_PG_mixamo_rig_props)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.xxmi_mixamo_rig_props
