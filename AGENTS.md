# XXMI-Toolbox 에이전트 가이드

이 문서는 XXMI-Toolbox 블렌더 애드온 개발 시 AI 에이전트가 준수해야 할 규칙과 프로젝트 구조를 정의합니다.

## 프로젝트 구조 (Architecture)
- **`__init__.py`**: 블렌더 애드온 메인 진입점. 버전을 관리하고 `source` 하위 모듈들을 로드합니다.
- **`source/`**: 애드온의 핵심 기능들이 모듈별로 나뉘어 있는 디렉토리입니다.
  - 각 기능은 독립적인 폴더를 가집니다 (예: `convert_shadow`, `copy_metadata`, `separate_by_vertex_group`).
  - 기능 폴더 내부 구조:
    - `properties.py`: UI 입력 및 데이터 저장을 위한 `PropertyGroup` 정의.
    - `operators.py`: 실제 동작을 수행하는 기능 로직 정의 (`Operator`).
    - `panel.py`: 3D 뷰포트 N-패널(`XXMI Toolbox` 탭)에 표시될 UI 레이아웃 정의.
    - `__init__.py`: 해당 모듈의 클래스들을 블렌더에 등록(Register)/해제(Unregister)합니다.
- **`standalones/`**: 패널 없이 블렌더 `Scripting` 워크스페이스에서 텍스트로 바로 실행할 수 있는 독립 스크립트 모음입니다.

## UI (패널) 디자인 컨벤션
블렌더 N-패널에 새로운 기능을 추가할 때 다음의 UI 규칙을 반드시 따릅니다:

1. **헤더 레이아웃 (커스텀 아이콘 표시)**:
   - `bl_label = ""`로 패널의 기본 이름을 비워둡니다.
   - `draw_header(self, context)`를 오버라이드하여 `layout.label(text="패널 이름", icon='원하는_아이콘')` 형태로 제목과 아이콘을 직접 그립니다.
   - **[주의/예외] `updator` 패널은 이 규칙에서 예외입니다. 또한, 앞으로 어떤 공통 UI 변경이나 기능 추가 작업이 발생하더라도 `updator` 패널 코드는 절대 임의로 수정하지 마십시오.**

2. **우측 상단 툴팁(도움말) 버튼 배치**:
   - 패널의 설명은 패널 내용(Content) 내부 우측 상단에 툴팁 버튼(`?` 아이콘)으로 제공합니다.
   - `draw(self, context)` 메서드 최상단에 아래 코드를 추가합니다:
     ```python
     row = layout.row()
     row.alignment = 'RIGHT'
     op = row.operator("object.xxmi_help_tooltip", text="", icon='QUESTION', emboss=False)
     op.text = "해당 패널 기능에 대한 설명 텍스트..."
     ```
   
3. **입력 필드 정렬 (`use_property_split`)**:
   - 라벨 텍스트와 입력 필드를 깔끔하게 정렬하기 위해 속성 스플릿을 항상 켭니다:
     ```python
     layout.use_property_split = True
     layout.use_property_decorate = False
     ```

## 스탠드얼론 (Standalone) 스크립트 컨벤션
스탠드얼론 스크립트는 패널이나 프로퍼티가 없으므로 다음 규칙을 따릅니다:
1. **주석 설명**: 스크립트 최상단에 사용 방법(선택 순서, 단축키 등)을 직관적으로 명시합니다.
2. **타겟 지정 방식**: 
   - 단일 대상: `bpy.context.active_object`를 기준으로 삼습니다.
   - 복수 대상: `bpy.context.selected_objects`를 사용하며, Ctrl+클릭으로 다중 선택한 뒤, 가장 마지막에 선택된 `Active Object`를 주요 타겟으로 지정하는 방식을 주로 사용합니다.
3. **에러 핸들링**: 에러 발생 시 콘솔 로그(`print()`) 뿐만 아니라, 블렌더 팝업 메뉴(`bpy.context.window_manager.popup_menu`)를 활용해 사용자에게 명시적으로 에러를 보여줍니다.

## 블렌더 API 컨벤션 및 주의사항
1. **Property Group**: `PointerProperty` 등 선언 시 `type` 인자를 생략하면 등록 시 에러가 발생할 수 있으므로 반드시 타입을 명시합니다.
2. **뷰포트 숨김 (Visibility) 처리**: `bpy.ops`를 사용하는 오퍼레이터(예: `bpy.ops.mesh.separate`)는 대상 메쉬나 부모 컬렉션이 뷰포트에서 숨겨져(`hide_viewport = True`) 있거나 선택 불가능(`hide_select = True`) 상태면 런타임 에러를 발생시킵니다. 작업 전 상태를 강제로 해제하거나, 가시성이 확보된 씬(Scene) 최상단에 임시로 컬렉션을 만들어 링크하는 방식 등으로 우회해야 합니다.
3. **커스텀 속성 유지**: XXMI Tools는 메쉬(`.data`)와 오브젝트(`.obj`) 단위에 부여된 커스텀 속성들을 참조하여 결과물을 처리합니다. 메타데이터 조작/복사 기능 구현 시 `_RNA_UI`를 제외한 커스텀 속성이 누락되지 않도록 유의합니다.
