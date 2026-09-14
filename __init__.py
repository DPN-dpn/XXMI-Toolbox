bl_info = {
    "name": "XXMI Toolbox",
    "author": "DPN",
    "version": (0, 1, 0),
    "blender": (2, 80, 0),
    "location": "N-Panel > Tool > XXMI Toolbox",
    "description": "XXMI모드의 여러 툴을 한 번에 관리합니다.",
    "category": "3D View",
}

# 임포트
from . import source

def register():
    source.register()

def unregister():
    source.unregister()

if __name__ == "__main__":
    register()
