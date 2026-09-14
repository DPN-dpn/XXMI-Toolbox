import bpy
from bpy.types import Panel

class XXMI_TOOLBOX_PT_updater(Panel):
    bl_label = "업데이트"
    bl_idname = "XXMI_TOOLBOX_PT_updater"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "XXMI Toolbox"
    bl_order = 9
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        latest_version = scene.get("xxmi_toolbox_latest_version", "")
        current_version = scene.get("xxmi_toolbox_current_version", "")
        update_available = scene.get("xxmi_toolbox_update_available", False)
        show_restart = scene.get("xxmi_toolbox_show_restart", False)

        if not latest_version:
            update_label = "업데이트 체크 필요"
        elif not update_available:
            update_label = "현재 최신 버전입니다"
        else:
            update_label = f"업데이트: {current_version} → {latest_version}"

        layout.operator("xxmi_toolbox.check_update", text="업데이트 체크", icon="FILE_REFRESH")
        
        row = layout.row()
        if show_restart:
            row.operator("wm.quit_blender", text="블렌더 종료(애드온 재실행)", icon="CANCEL")
        else:
            row.enabled = bool(update_available)
            row.operator("xxmi_toolbox.do_update", text=update_label, icon="IMPORT")
            
        layout.operator("xxmi_toolbox.open_github", text="GitHub", icon="URL")

classes = (
    XXMI_TOOLBOX_PT_updater,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
