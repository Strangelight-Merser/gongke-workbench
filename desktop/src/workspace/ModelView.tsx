import { useEffect, useRef } from "react";
import * as THREE from "three";
import { toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import type { Data } from "../api";

function dispose(group: THREE.Group) {
  group.traverse((o) => {
    if (o instanceof THREE.Mesh || o instanceof THREE.Line) {
      o.geometry.dispose();
      (o.material as THREE.Material).dispose();
    }
  });
  group.clear();
}
const vector = (p: number[]) => new THREE.Vector3(p[0], p[1], p[2]);
export function ModelView({
  scene,
  selected,
  onSelect,
  detail,
  checks,
  focusRequest = 0,
}: {
  scene: Data;
  selected: string;
  onSelect(id: string): void;
  detail?: Data | null;
  checks?: Data;
  focusRequest?: number;
}) {
  const focused = useRef(0);
  const mount = useRef<HTMLDivElement>(null);
  const view = useRef<{
    world: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    models: THREE.Group;
    overlays: THREE.Group;
    fitted: string | null;
  } | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  useEffect(() => {
    const element = mount.current!;
    const world = new THREE.Scene(),
      camera = new THREE.PerspectiveCamera(42, 1, 0.001, 1e7);
    camera.up.set(0, 0, 1);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    const models = new THREE.Group(),
      overlays = new THREE.Group();
    world.add(models, overlays);
    world.add(new THREE.HemisphereLight(0xffffff, 0x8f8b85, 2.6));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(2, 4, 3);
    world.add(light);
    const theme = () => {
      const base = new THREE.Color(
        getComputedStyle(element).getPropertyValue("--surface-base").trim() ||
          "#242422",
      );
      world.background = null;
      renderer.setClearColor(0x000000, 0);
      const top = base.clone().lerp(new THREE.Color("#ffffff"), 0.24);
      element.style.background = `linear-gradient(145deg, #${top.getHexString()}, #${base.getHexString()})`;
    };
    theme();
    const observer = new MutationObserver(theme);
    const root = element.closest(".workbench");
    if (root)
      observer.observe(root, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
    const resize = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      for (const overlay of overlays.children) {
        if (overlay instanceof Line2)
          overlay.material.resolution.set(width, height);
      }
      const box = new THREE.Box3().setFromObject(models);
      if (!box.isEmpty()) {
        const center = box.getCenter(new THREE.Vector3());
        const direction = camera.position
          .clone()
          .sub(controls.target)
          .normalize();
        const distance =
          (box.getSize(new THREE.Vector3()).length() * 1.1) /
          Math.min(1, camera.aspect);
        camera.position.copy(center).addScaledVector(direction, distance);
        controls.target.copy(center);
        controls.update();
      }
    });
    resize.observe(element);
    let down = { x: 0, y: 0 };
    const ray = new THREE.Raycaster();
    const pointerDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY };
    };
    const pointerUp = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return;
      const r = element.getBoundingClientRect();
      ray.setFromCamera(
        new THREE.Vector2(
          ((e.clientX - r.left) / r.width) * 2 - 1,
          1 - ((e.clientY - r.top) / r.height) * 2,
        ),
        camera,
      );
      const hit = ray.intersectObjects(models.children)[0];
      if (hit) select.current(hit.object.userData.id);
    };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    view.current = { world, camera, controls, models, overlays, fitted: null };
    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(world, camera);
    });
    return () => {
      renderer.setAnimationLoop(null);
      resize.disconnect();
      observer.disconnect();
      controls.dispose();
      dispose(models);
      dispose(overlays);
      renderer.dispose();
      renderer.domElement.remove();
      view.current = null;
    };
  }, []);
  useEffect(() => {
    const v = view.current!;
    dispose(v.models);
    for (const item of scene.objects || []) {
      if (!item.vertices?.length || !item.triangles?.length) continue;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(item.vertices.flat(), 3),
      );
      geometry.setIndex(item.triangles.flat());
      const shaded = toCreasedNormals(geometry, Math.PI / 6);
      geometry.dispose();
      const mesh = new THREE.Mesh(
        shaded,
        new THREE.MeshStandardMaterial({
          color: "#8e8b86",
          metalness: 0.32,
          roughness: 0.46,
          side: THREE.DoubleSide,
        }),
      );
      mesh.userData.id = item.id;
      v.models.add(mesh);
    }
  }, [scene]);
  useEffect(() => {
    const v = view.current!;
    dispose(v.overlays);
    for (const object of v.models.children)
      ((object as THREE.Mesh).material as THREE.MeshStandardMaterial).color.set(
        object.userData.id === selected ? "#e8742a" : "#8e8b86",
      );
    function line(points: number[][], color: string, depthTest = false) {
      if (points.length < 2) return;
      if (!depthTest) {
        const geometry = new LineGeometry();
        geometry.setPositions(
          points.flatMap((p) => vector(p).multiplyScalar(1000).toArray()),
        );
        const material = new LineMaterial({
          color,
          linewidth: 4,
          depthTest: false,
          depthWrite: false,
        });
        material.resolution.set(
          mount.current!.clientWidth,
          mount.current!.clientHeight,
        );
        const object = new Line2(geometry, material);
        object.renderOrder = 2;
        v.overlays.add(object);
        return;
      }
      const geometry = new THREE.BufferGeometry().setFromPoints(
        points.map((p) => vector(p).multiplyScalar(1000)),
      );
      const object = new THREE.Line(
        geometry,
        new THREE.LineBasicMaterial({ color, depthTest }),
      );
      object.renderOrder = 2;
      v.overlays.add(object);
    }
    for (const edge of detail?.edges || [])
      line(edge.samples || [edge.start, edge.end], "#e8742a", true);
    const box = new THREE.Box3().setFromObject(v.models);
    box.union(new THREE.Box3().setFromObject(v.overlays));
    const center = box.getCenter(new THREE.Vector3()),
      size = box.getSize(new THREE.Vector3()).length() || 100;
    if (!box.isEmpty() && v.fitted !== scene.session_id) {
      v.camera.position
        .copy(center)
        .add(new THREE.Vector3(size * 0.9, -size * 0.9, size * 0.6));
      v.controls.target.copy(center);
      v.fitted = scene.session_id;
      v.controls.update();
    }
    if (focusRequest !== focused.current && detail?.object_ref === selected) {
      const targetBox = new THREE.Box3().setFromObject(v.overlays);
      if (!targetBox.isEmpty()) {
        const target = targetBox.getCenter(new THREE.Vector3());
        const distance =
          targetBox.getSize(new THREE.Vector3()).length() * 1.8 || size;
        const direction = v.camera.position
          .clone()
          .sub(v.controls.target)
          .normalize();
        v.camera.position.copy(target).addScaledVector(direction, distance);
        v.controls.target.copy(target);
        v.controls.update();
      }
      focused.current = focusRequest;
    }
    v.camera.near = size / 10000;
    v.camera.far = Math.max(size * 100, v.camera.position.length() * 10);
    v.camera.updateProjectionMatrix();
    for (const check of checks?.checks || []) {
      if (check.status !== "fail") continue;
      for (const location of check.actual?.locations || []) {
        const snapshots = scene.snapshots || [];
        const edge = snapshots
          .flatMap((s: Data) => s.edges || [])
          .find((e: Data) => e.native_ref === location.native_ref);
        if (edge) {
          line(edge.samples || [edge.start, edge.end], "#e54b4b");
          continue;
        }
        const face = (scene.objects || [])
          .flatMap((o: Data) => o.faces || [])
          .find((f: Data) => f.native_ref === location.native_ref);
        if (face?.triangles?.length) {
          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute(
            "position",
            new THREE.Float32BufferAttribute(face.vertices.flat(), 3),
          );
          geometry.setIndex(face.triangles.flat());
          const marker = new THREE.Mesh(
            geometry,
            new THREE.MeshBasicMaterial({
              color: "#e54b4b",
              transparent: true,
              opacity: 0.42,
              side: THREE.DoubleSide,
              depthWrite: false,
              polygonOffset: true,
              polygonOffsetFactor: -2,
              polygonOffsetUnits: -2,
            }),
          );
          marker.renderOrder = 3;
          v.overlays.add(marker);
        } else if (location.edges) {
          for (const edge of location.edges)
            line(
              edge.samples || [edge.start, edge.end],
              location.difference === "missing_or_shifted"
                ? "#3f9a62"
                : "#e54b4b",
            );
        } else if (detail?.object_ref === location.native_ref) {
          for (const e of detail?.edges || [])
            line(e.samples || [e.start, e.end], "#e54b4b");
        }
      }
    }
  }, [scene, selected, detail, checks, focusRequest]);
  return (
    <div className="model-view" ref={mount}>
      <span className="viewport-hint">
        拖动旋转 · 滚轮缩放 · 点击选择
        {checks?.status === "fail"
          ? " · 红色：模型不符边；青绿：图纸要求的位置"
          : ""}
      </span>
    </div>
  );
}
