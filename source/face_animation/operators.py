import bpy
import struct
import os
import re
import json
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

def find_target_ini(folder_path, blend_hash):
    """지정된 폴더 및 하위 폴더에서 해당 얼굴 해시를 포함하는 ini 파일을 찾습니다. (disabled로 시작하면 무시)"""
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.lower().startswith('disabled')]
        for file in files:
            if file.lower().endswith('.ini') and not file.lower().startswith('disabled'):
                ini_path = os.path.join(root, file)
                try:
                    with open(ini_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip().lower() == f"hash = {blend_hash.lower()}":
                                return ini_path
                except:
                    pass
    return None

def do_rollback_internal(ini_path):
    """INI 파일 경로를 받아 애니메이션 관련 생성 파일을 삭제하고 INI를 원상 복구합니다."""
    if not os.path.isfile(ini_path):
        return

    mod_folder = os.path.dirname(ini_path)

    map_pattern = re.compile(r"^FaceAnimationMap_\d+\.buf$")
    hlsl_pattern = re.compile(r"^FaceAnimation_\d+\.hlsl$")
    
    try:
        for fname in os.listdir(mod_folder):
            if fname in ("FaceOriginalNeutral.buf", "FaceAnimationMap.buf", "FaceAnimation.hlsl") or map_pattern.match(fname) or hlsl_pattern.match(fname):
                fpath = os.path.join(mod_folder, fname)
                os.remove(fpath)
    except:
        pass

    try:
        with open(ini_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        extracted_files = {}
        current_idx = None
        for line in lines:
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                sec = l[1:-1].strip()
                if sec.startswith("resourcecustomfaceextracted"):
                    parts = sec.split("_")
                    current_idx = parts[-1] if len(parts) > 1 and parts[-1].isdigit() else ""
                else:
                    current_idx = None
            elif current_idx is not None and l.startswith("filename"):
                parts = line.split('=', 1)
                if len(parts) == 2:
                    extracted_files[current_idx] = parts[1].strip().lower().replace('\\', '/')

        orig_resources = {}
        current_res = None
        for line in lines:
            l = line.strip()
            if l.startswith('[') and l.endswith(']'):
                current_res = l[1:-1].strip()
            elif current_res and not current_res.lower().startswith('resourcecustomfaceextracted') and l.lower().startswith('filename'):
                parts = line.split('=', 1)
                if len(parts) == 2:
                    fname = parts[1].strip().lower().replace('\\', '/')
                    for idx, ex_fname in extracted_files.items():
                        if fname == ex_fname:
                            orig_resources[idx] = current_res

        out_lines = []
        for line in lines:
            l = line.strip().lower()
            if l == "; xxmi face animation auto-injected":
                while out_lines and out_lines[-1].strip() in ("", "; =========================================================="):
                    out_lines.pop()
                break  
                
            if l.startswith("run ") and "customshaderfaceanimation" in l:
                continue
                
            if l.startswith("vb0 ") or l.startswith("vb0="):
                if "resourcefaceanimated" in l:
                    res_val = line.split("=", 1)[1].strip()
                    parts = res_val.split("_")
                    idx = parts[-1] if len(parts) > 1 and parts[-1].isdigit() else ""
                    
                    orig_res = orig_resources.get(idx)
                    if orig_res:
                        indent = line[:len(line) - len(line.lstrip())]
                        out_lines.append(f"{indent}vb0 = {orig_res}\n")
                    continue
                    
            out_lines.append(line)

        with open(ini_path, 'w', encoding='utf-8') as f:
            f.writelines(out_lines)
    except:
        pass

class XXMI_OT_export_face_animation(bpy.types.Operator):
    bl_idname = "object.xxmi_export_face_animation"
    bl_label = "표정 연동 실행"
    bl_description = "선택된 파일들을 분석하여 표정 연동 데이터를 생성하고 ini 파일을 수정합니다"
    
    def execute(self, context):
        props = context.scene.xxmi_face_anim_props
        
        dump_hash_json = props.dump_hash_json
        selected_comp = props.selected_component
        target_ini_input = props.target_ini
        
        if not os.path.isfile(dump_hash_json):
            self.report({'ERROR'}, "에셋 hash.json 파일을 올바르게 지정해주세요.")
            return {'CANCELLED'}
            
        dump_folder = os.path.dirname(dump_hash_json)
        
        if selected_comp == "NONE":
            self.report({'ERROR'}, "얼굴 컴포넌트를 선택해주세요.")
            return {'CANCELLED'}
            
        if not target_ini_input:
            self.report({'ERROR'}, "타겟 모드 ini 파일(또는 폴더)을 지정해주세요.")
            return {'CANCELLED'}
            
        try:
            # 1. hash.json 파싱
            hash_path = os.path.join(dump_folder, "hash.json")
            if not os.path.isfile(hash_path):
                hash_path = dump_hash_json
                
            with open(hash_path, 'r', encoding='utf-8') as f:
                hash_data = json.load(f)
                
            comp_data = next((c for c in hash_data if c.get("component_name") == selected_comp), None)
            if not comp_data:
                self.report({'ERROR'}, f"hash.json에서 {selected_comp} 컴포넌트를 찾을 수 없습니다.")
                return {'CANCELLED'}
                
            pos_vb_hash = comp_data.get("position_vb")
            ib_hash = comp_data.get("ib")
            blend_vb_hash = comp_data.get("blend_vb")
            
            if not pos_vb_hash or not ib_hash:
                self.report({'ERROR'}, "컴포넌트에 필요한 해시(position_vb, ib)가 부족합니다.")
                return {'CANCELLED'}
                
            # 2. 타겟 INI 찾기 및 롤백 초기화
            if os.path.isdir(target_ini_input):
                target_ini = find_target_ini(target_ini_input, blend_vb_hash)
            elif os.path.isfile(target_ini_input):
                target_ini = target_ini_input
            else:
                target_ini = None

            if not target_ini or not os.path.isfile(target_ini):
                self.report({'ERROR'}, f"{target_ini_input} 경로에서 얼굴 컴포넌트(hash={blend_vb_hash})가 있는 유효한 ini 파일을 찾을 수 없습니다.")
                return {'CANCELLED'}
                
            # 초기화 (이미 적용된 내용 롤백)
            do_rollback_internal(target_ini)
            mod_folder = os.path.dirname(target_ini)
                
            # 3. 덤프 텍스트 파일 찾기
            vb0_txt = self.find_file_with_hash(dump_folder, pos_vb_hash, "-vb0=")
            ib_txt = self.find_file_with_hash(dump_folder, ib_hash, "-ib=")
            
            if not vb0_txt or not ib_txt:
                self.report({'ERROR'}, f"에셋 폴더에서 {selected_comp}의 -vb0 또는 -ib 텍스트 파일을 찾을 수 없습니다.")
                return {'CANCELLED'}
                
            # 4. .ini 파싱 및 다중 커스텀 buf 경로 추적
            buffers_list, ini_lines = self.parse_and_get_custom_bufs(target_ini, blend_vb_hash)
            if not buffers_list:
                self.report({'ERROR'}, "ini 파일에서 커스텀 얼굴 버퍼를 추적할 수 없습니다.")
                return {'CANCELLED'}
                
            # 5. txt 파싱 및 FaceOriginalNeutral.buf 굽기
            orig_vertices, orig_polygons, orig_vertex_count = self.parse_dump_txt(vb0_txt, ib_txt, os.path.join(mod_folder, "FaceOriginalNeutral.buf"))
            
            bvh_vertices = orig_vertices
            if props.aligned_orig_base:
                mesh = props.aligned_orig_base.data
                if len(mesh.vertices) == orig_vertex_count:
                    bvh_vertices = [v.co for v in mesh.vertices]
                else:
                    self.report({'WARNING'}, f"형태 맞춤 오브젝트의 버텍스 개수({len(mesh.vertices)})가 덤프({orig_vertex_count})와 다릅니다. 원본 좌표를 사용합니다.")
                    
            bvh = BVHTree.FromPolygons(bvh_vertices, orig_polygons)
            
            # 6. 다중 버퍼(애니메이션 프레임) 맵핑 진행
            custom_buffers_info = []
            
            wm = context.window_manager
            wm.progress_begin(0, len(buffers_list))
            
            for idx, (res_key, buf_filename) in enumerate(buffers_list):
                custom_buf_path = os.path.join(mod_folder, buf_filename)
                if not os.path.isfile(custom_buf_path):
                    self.report({'ERROR'}, f"커스텀 버퍼 파일이 존재하지 않습니다: {buf_filename}")
                    wm.progress_end()
                    return {'CANCELLED'}
                    
                map_out_path = os.path.join(mod_folder, f"FaceAnimationMap_{idx}.buf")
                custom_vertex_count = self.build_animation_map(
                    custom_buf_path, bvh, bvh_vertices, orig_polygons, 
                    map_out_path, props.mapping_method
                )
                
                self.export_hlsl(mod_folder, props.use_custom_blink, custom_vertex_count, orig_vertex_count, idx)
                custom_buffers_info.append((res_key, buf_filename, custom_vertex_count))
                wm.progress_update(idx + 1)
                
            wm.progress_end()
            
            # 7. INI 주입 (Inject)
            self.inject_ini(target_ini, ini_lines, custom_buffers_info, blend_vb_hash, props.use_custom_blink)
            
            # 완료 알림
            def draw_popup(self, context):
                self.layout.label(text="[표정 연동 완료]", icon='INFO')
                self.layout.label(text=f"총 {len(buffers_list)}개의 버퍼가 성공적으로 연동되었습니다.")
                self.layout.label(text="모드 ini 파일에 다중 쉐이더 구문이 적용되었습니다.")

            context.window_manager.popup_menu(draw_popup, title="연동 완료", icon='INFO')
            self.report({'INFO'}, "표정 연동이 완료되었습니다.")
            return {'FINISHED'}
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"에러 발생: {str(e)}")
            return {'CANCELLED'}
            
    def find_file_with_hash(self, folder, hash_val, keyword):
        for f in os.listdir(folder):
            if keyword in f and hash_val in f and f.endswith(".txt"):
                return os.path.join(folder, f)
        return None
        
    def parse_and_get_custom_bufs(self, ini_path, blend_hash):
        with open(ini_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        hash_section = None
        in_any_section = None
        
        for line in lines:
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                in_any_section = l[1:-1].strip()
            elif l == f"hash = {blend_hash.lower()}":
                hash_section = in_any_section
                
        if not hash_section:
            return [], lines
            
        target_commands = [hash_section.lower()]
        in_hash_section = False
        for line in lines:
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                in_hash_section = (l[1:-1].strip() == hash_section.lower())
            elif in_hash_section and (l.startswith("run ") or l.startswith("run=")):
                run_val = l.split("=", 1)[1].strip()
                if run_val not in target_commands:
                    target_commands.append(run_val)
                    
        resource_keys = [] 
        in_target_cmd = False
        
        for line in lines:
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                in_target_cmd = (l[1:-1].strip() in target_commands)
                
            if in_target_cmd:
                if l.startswith("vb0 ") or l.startswith("vb0="):
                    res_val = l.split("=", 1)[1].strip()
                    if not res_val.startswith("resourcefaceanimated") and res_val not in resource_keys:
                        resource_keys.append(res_val)
                elif l.startswith("cs-u5") and "copy" in l:
                    res_val = l.split("copy", 1)[1].strip()
                    if res_val != "resourcefaceexpressionbase" and res_val not in resource_keys:
                        resource_keys.append(res_val)
                        
        buffers = []
        for res_key in resource_keys:
            in_res = False
            for line in lines:
                l = line.strip().lower()
                if l.startswith('[') and l.endswith(']'):
                    in_res = (l[1:-1].strip() == res_key.lower())
                elif in_res and l.startswith("filename"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        buffers.append((res_key, parts[1].strip()))
                        break
                        
        return buffers, lines
        
    def parse_dump_txt(self, vb0_path, ib_path, out_buf_path):
        vertices = []
        buf_data = bytearray()
        vertex_count = 0
        
        with open(vb0_path, 'r', encoding='utf-8') as f:
            current_pos = [0.0, 0.0, 0.0]
            current_norm = [0.0, 0.0, 0.0]
            current_tang = [0.0, 0.0, 0.0, 0.0]
            
            for line in f:
                l = line.strip()
                if l.startswith("vertex count:"):
                    vertex_count = int(l.split(":")[1].strip())
                    
                if "POSITION:" in l:
                    vals = l.split("POSITION:")[1].strip().split(",")
                    current_pos = [float(v.strip()) for v in vals]
                    vertices.append(Vector(current_pos))
                    
                elif "NORMAL:" in l:
                    vals = l.split("NORMAL:")[1].strip().split(",")
                    current_norm = [float(v.strip()) for v in vals]
                    
                elif "TANGENT:" in l:
                    vals = l.split("TANGENT:")[1].strip().split(",")
                    current_tang = [float(v.strip()) for v in vals]
                    
                    buf_data.extend(struct.pack('<3f', *current_pos))
                    buf_data.extend(struct.pack('<3f', *current_norm))
                    buf_data.extend(struct.pack('<4f', *current_tang))
                    
        with open(out_buf_path, 'wb') as f:
            f.write(buf_data)
            
        polygons = []
        with open(ib_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                l = line.strip()
                if not l or l.startswith("byte") or l.startswith("first") or l.startswith("index") or l.startswith("topology") or l.startswith("format"):
                    continue
                parts = l.split()
                if len(parts) >= 3:
                    polygons.append((int(parts[0]), int(parts[1]), int(parts[2])))
                    
        return vertices, polygons, vertex_count
        
    def build_animation_map(self, custom_buf_path, bvh, orig_vertices, orig_polygons, out_map_path, mapping_method):
        from mathutils.geometry import barycentric_transform
        
        custom_vertex_count = 0
        map_data = bytearray()
        
        with open(custom_buf_path, 'rb') as f:
            while True:
                pos_bytes = f.read(12)
                if not pos_bytes or len(pos_bytes) < 12:
                    break
                norm_bytes = f.read(12)
                f.read(16) 
                
                custom_vertex_count += 1
                pos = struct.unpack('<3f', pos_bytes)
                v_pos = Vector(pos)
                norm = struct.unpack('<3f', norm_bytes)
                v_norm = Vector(norm)
                if v_norm.length > 0:
                    v_norm.normalize()
                
                if mapping_method == 'TOPOLOGY':
                    idx = min(custom_vertex_count - 1, len(orig_vertices) - 1)
                    struct_data = struct.pack('<3I 3I 3f 3f', idx, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                    map_data.extend(struct_data)
                    continue
                    
                if mapping_method == 'NEAREST_VERTEX':
                    location, normal, index, distance = bvh.find_nearest(v_pos)
                    if location is None:
                        struct_data = struct.pack('<3I 3I 3f 3f', 0,0,0, 0,0,0, 1.0,0.0,0.0, 0.0,0.0,0.0)
                    else:
                        poly = orig_polygons[index]
                        dists = [ (v_pos - orig_vertices[i]).length for i in poly ]
                        min_i = poly[dists.index(min(dists))]
                        struct_data = struct.pack('<3I 3I 3f 3f', min_i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                    map_data.extend(struct_data)
                    continue
                    
                location = None
                index = -1
                
                if mapping_method == 'PROJECTED_FACE_INTERPOLATED':
                    location, normal, index, distance = bvh.ray_cast(v_pos - v_norm * 0.1, v_norm)
                    if location is None:
                        location, normal, index, distance = bvh.ray_cast(v_pos + v_norm * 0.1, -v_norm)
                        
                if location is None:
                    location, normal, index, distance = bvh.find_nearest(v_pos)
                    
                if location is None:
                    struct_data = struct.pack('<3I 3I 3f 3f', 0,0,0, 0,0,0, 1.0,0.0,0.0, 0.0,0.0,0.0)
                    map_data.extend(struct_data)
                    continue
                    
                poly = orig_polygons[index]
                
                if mapping_method == 'NEAREST_FACE_VERTEX':
                    dists = [ (location - orig_vertices[i]).length for i in poly ]
                    min_i = poly[dists.index(min(dists))]
                    struct_data = struct.pack('<3I 3I 3f 3f', min_i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                else:
                    p1 = orig_vertices[poly[0]]
                    p2 = orig_vertices[poly[1]]
                    p3 = orig_vertices[poly[2]]
                    
                    try:
                        weights = barycentric_transform(location, p1, p2, p3, Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1)))
                        w0, w1, w2 = weights.x, weights.y, weights.z
                    except Exception:
                        w0, w1, w2 = 1.0, 0.0, 0.0
                        
                    struct_data = struct.pack('<3I 3I 3f 3f', poly[0], poly[1], poly[2], 0, 0, 0, w0, w1, w2, 0.0, 0.0, 0.0)
                    
                map_data.extend(struct_data)
                
        with open(out_map_path, 'wb') as f:
            f.write(map_data)
            
        return custom_vertex_count
        
    def export_hlsl(self, directory, use_custom_blink, custom_vtx_count, orig_vtx_count, suffix_idx):
        hlsl_code = f"""// Transfer live pre-skinning facial deformation to the custom face.
struct Vertex {{
    float3 position;
    float3 normal;
    float4 tangent;
}};
struct Attachment {{
    uint3 first;
    uint3 second;
    float3 firstWeights;
    float3 secondWeights;
}};

StructuredBuffer<Vertex> Live : register(t50);
StructuredBuffer<Vertex> Neutral : register(t51);
StructuredBuffer<Attachment> Map : register(t52);
RWStructuredBuffer<Vertex> Output : register(u5);

float3 residual(uint index) {{
    return Live[index].position - Neutral[index].position;
}}

[numthreads(64, 1, 1)]
void main(uint3 threadID : SV_DispatchThreadID) {{
    uint i = threadID.x;
    if (i >= {custom_vtx_count}) return;
    uint sourceCount, sourceStride;
    Live.GetDimensions(sourceCount, sourceStride);
    if (sourceCount != {orig_vtx_count} || sourceStride != 40) return;
    Attachment a = Map[i];
    float3 delta = 0;
    [unroll] for (uint j = 0; j < 3; ++j) {{
        if (a.firstWeights[j] != 0)
            delta += residual(a.first[j]) * a.firstWeights[j];
        if (a.secondWeights[j] != 0)
            delta += residual(a.second[j]) * a.secondWeights[j];
    }}
    
    Vertex vertex = Output[i];
    vertex.position += delta;
    Output[i] = vertex;
}}
"""
        with open(os.path.join(directory, f"FaceAnimation_{suffix_idx}.hlsl"), 'w', encoding='utf-8') as f:
            f.write(hlsl_code)
            
    def inject_ini(self, ini_path, lines, custom_buffers, blend_hash, use_custom_blink):
        hash_section = None
        in_any_section = None
        
        for line in lines:
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                in_any_section = l[1:-1].strip()
            elif l == f"hash = {blend_hash.lower()}":
                hash_section = in_any_section
                
        target_commands = [hash_section.lower()] if hash_section else []
        in_hash_section = False
        for line in lines:
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                in_hash_section = (l[1:-1].strip() == hash_section.lower()) if hash_section else False
            elif in_hash_section and (l.startswith("run ") or l.startswith("run=")):
                run_val = l.split("=", 1)[1].strip()
                if run_val not in target_commands:
                    target_commands.append(run_val)
                    
        out_lines = []
        in_target_cmd = False
        in_draw_type_1 = False
        
        for i, line in enumerate(lines):
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                in_target_cmd = (l[1:-1].strip() in target_commands)
                in_draw_type_1 = False
                
            if in_target_cmd:
                if "if draw_type" in l and "1" in l:
                    in_draw_type_1 = True
                elif "endif" in l or "elif" in l:
                    in_draw_type_1 = False
                    
                if in_draw_type_1 or not any("if draw_type" in x.lower() for x in lines):
                    if (l.startswith("vb0 ") or l.startswith("vb0=")) and "resourcefaceanimated" not in l:
                        res_val = line.split("=", 1)[1].strip()
                        idx = -1
                        for j, (rk, _, _) in enumerate(custom_buffers):
                            if rk.lower() == res_val.lower():
                                idx = j
                                break
                        if idx != -1:
                            indent = line[:len(line) - len(line.lstrip())]
                            out_lines.append(f"{indent}run = CustomShaderFaceAnimation_{idx}\n")
                            out_lines.append(f"{indent}vb0 = ResourceFaceAnimated_{idx}\n")
                            continue
                            
            out_lines.append(line)
            
        appended_ini = "\n; ==========================================================\n; XXMI Face Animation Auto-Injected\n; ==========================================================\n"
        appended_ini += "[ResourceFaceOriginalNeutral]\ntype = StructuredBuffer\nstride = 40\nfilename = FaceOriginalNeutral.buf\n\n"
        appended_ini += "[ResourceFaceLive]\ntype = StructuredBuffer\nstride = 40\n\n"
        
        for idx, (res_key, buf_filename, v_count) in enumerate(custom_buffers):
            dispatch_groups = math.ceil(v_count / 64.0)
            block = f"""[CustomShaderFaceAnimation_{idx}]
cs = FaceAnimation_{idx}.hlsl
ResourceFaceLive = copy vb0
cs-t50 = ref ResourceFaceLive
cs-t51 = ref ResourceFaceOriginalNeutral
cs-t52 = ref ResourceFaceAnimationMap_{idx}
cs-u5 = copy ResourceCustomFaceExtracted_{idx}
ResourceFaceAnimated_{idx} = ref cs-u5
Dispatch = {dispatch_groups}, 1, 1
cs-u5 = null
cs-t50 = null
cs-t51 = null
cs-t52 = null

[ResourceFaceAnimated_{idx}]

[ResourceFaceAnimationMap_{idx}]
type = StructuredBuffer
stride = 48
filename = FaceAnimationMap_{idx}.buf

[ResourceCustomFaceExtracted_{idx}]
type = StructuredBuffer
stride = 40
filename = {buf_filename}

"""
            appended_ini += block
            
        appended_ini += "; ==========================================================\n"
        out_lines.append(appended_ini)
        
        with open(ini_path, 'w', encoding='utf-8') as f:
            f.writelines(out_lines)

class XXMI_OT_file_picker(bpy.types.Operator):
    bl_idname = "object.xxmi_file_picker"
    bl_label = "파일 선택"
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="", options={'HIDDEN'})
    prop_name: bpy.props.StringProperty(options={'HIDDEN'})
    
    def execute(self, context):
        setattr(context.scene.xxmi_face_anim_props, self.prop_name, self.filepath)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class XXMI_OT_dir_picker(bpy.types.Operator):
    bl_idname = "object.xxmi_dir_picker"
    bl_label = "폴더 선택"
    
    directory: bpy.props.StringProperty(subtype="DIR_PATH")
    prop_name: bpy.props.StringProperty(options={'HIDDEN'})
    
    def execute(self, context):
        setattr(context.scene.xxmi_face_anim_props, self.prop_name, self.directory)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class XXMI_OT_rollback_face_animation(bpy.types.Operator):
    bl_idname = "object.xxmi_rollback_face_animation"
    bl_label = "연동 롤백"
    bl_description = "이미 표정 연동이 적용된 타겟 모드의 폴더를 선택하여 연동을 롤백합니다"
    
    directory: bpy.props.StringProperty(subtype="DIR_PATH")
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
        
    def execute(self, context):
        target_path = self.directory
        if os.path.isfile(target_path):
            do_rollback_internal(target_path)
        elif os.path.isdir(target_path):
            found = False
            for root, dirs, files in os.walk(target_path):
                dirs[:] = [d for d in dirs if not d.lower().startswith('disabled')]
                for file in files:
                    if file.lower().endswith('.ini') and not file.lower().startswith('disabled'):
                        do_rollback_internal(os.path.join(root, file))
                        found = True
            if not found:
                self.report({'ERROR'}, "롤백할 .ini 파일을 찾을 수 없습니다.")
                return {'CANCELLED'}
        else:
            self.report({'ERROR'}, "유효하지 않은 경로입니다.")
            return {'CANCELLED'}
                    
        def draw_popup(self, context):
            self.layout.label(text="[연동 롤백 완료]", icon='INFO')
            self.layout.label(text="ini 파일 복원 및 생성되었던 애니메이션 파일들이 모두 삭제되었습니다.")
            
        context.window_manager.popup_menu(draw_popup, title="롤백 완료", icon='INFO')
        self.report({'INFO'}, "표정 연동이 롤백되었습니다.")
        return {'FINISHED'}

classes = (
    XXMI_OT_export_face_animation,
    XXMI_OT_file_picker,
    XXMI_OT_dir_picker,
    XXMI_OT_rollback_face_animation,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
