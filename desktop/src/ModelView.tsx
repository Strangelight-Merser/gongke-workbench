import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { Data } from "./api";

export function ModelView({
  scene,
  selected,
  onSelect,
}: {
  scene: Data;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const mount = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!mount.current) return;
    const element = mount.current,
      world = new THREE.Scene();
    world.background = new THREE.Color(
      getComputedStyle(element).getPropertyValue("--surface-base").trim(),
    );
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1e7),
      renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    world.add(new THREE.HemisphereLight(0xffffff, 0x8a968f, 2.6));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(2, 4, 3);
    world.add(light);
    const group = new THREE.Group();
    world.add(group);
    const meshes: THREE.Mesh[] = [];
    for (const item of scene.objects || []) {
      if (!item.vertices?.length || !item.triangles?.length) continue;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(item.vertices.flat(), 3),
      );
      geometry.setIndex(item.triangles.flat());
      geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({
        color: item.id === selected ? "#23508a" : "#a9b6ae",
        metalness: 0.32,
        roughness: 0.46,
        side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData.id = item.id;
      group.add(mesh);
      meshes.push(mesh);
    }
    const box = new THREE.Box3().setFromObject(group),
      center = box.getCenter(new THREE.Vector3()),
      size = box.getSize(new THREE.Vector3()).length() || 100;
    group.position.sub(center);
    camera.position.set(size * 0.9, size * 0.5, size * 0.9);
    camera.far = size * 100;
    camera.near = size / 10000;
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.update();
    const grid = new THREE.GridHelper(size * 2, 20, 0x38434d, 0x28323c);
    grid.position.y = -box.getSize(new THREE.Vector3()).y / 2 - 1;
    world.add(grid);
    const resize = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    });
    resize.observe(element);
    const ray = new THREE.Raycaster();
    let down = { x: 0, y: 0 };
    const pointerDown = (event: PointerEvent) => {
      down = { x: event.clientX, y: event.clientY };
    };
    const pointerUp = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - down.x, event.clientY - down.y) > 4)
        return;
      const r = element.getBoundingClientRect();
      ray.setFromCamera(
        new THREE.Vector2(
          ((event.clientX - r.left) / r.width) * 2 - 1,
          1 - ((event.clientY - r.top) / r.height) * 2,
        ),
        camera,
      );
      const hit = ray.intersectObjects(meshes)[0];
      if (hit) onSelect(hit.object.userData.id);
    };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(world, camera);
    });
    return () => {
      renderer.setAnimationLoop(null);
      resize.disconnect();
      controls.dispose();
      for (const mesh of meshes) {
        mesh.geometry.dispose();
        (mesh.material as THREE.Material).dispose();
      }
      grid.geometry.dispose();
      (grid.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [scene, selected, onSelect]);
  return (
    <div className="model-view" ref={mount}>
      <span className="viewport-hint">拖动旋转 · 滚轮缩放 · 点击选择</span>
    </div>
  );
}
