bl_info = {
    "name": "XXMI Toolbox",
    "author": "DPN",
    "version": (1, 2, 0),
    "blender": (2, 80, 0),
    "location": "N-Panel > Tool > XXMI Toolbox",
    "description": "XXMI 모딩을 위한 유용한 툴을 모아놓은 에디터 확장 기능",
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
