import bpy

class XXMI_PG_separate_mesh_props(bpy.types.PropertyGroup):
    target_obj: bpy.props.PointerProperty(
        name="타겟 메쉬",
        type=bpy.types.Object,
        description="분리할 대상 메쉬 오브젝트"
    )
    ignore_connectivity: bpy.props.BoolProperty(
        name="메쉬 강제 분리",
        description="체크 시 물리적으로 연결되어 있더라도 버텍스 그룹이 다르면 강제로 분리합니다",
        default=False
    )

classes = (
    XXMI_PG_separate_mesh_props,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.xxmi_separate_mesh_props = bpy.props.PointerProperty(type=XXMI_PG_separate_mesh_props)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.xxmi_separate_mesh_props
