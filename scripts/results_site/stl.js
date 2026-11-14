// A part's mesh as an STL file, made in the browser from the same .glb the 3D view shows: millimetres, Z up, as the
// model wrote it. three.js and its exporter are fetched only when a reader asks for a file.

export async function downloadStl(url, filename) {
  const [{ GLTFLoader }, { STLExporter }] = await Promise.all([
    import("three/addons/loaders/GLTFLoader.js"),
    import("three/addons/exporters/STLExporter.js"),
  ]);
  const gltf = await new Promise((resolve, reject) => new GLTFLoader().load(url, resolve, undefined, () => reject(new Error("the mesh file didn't load"))));
  gltf.scene.updateMatrixWorld(true);
  const data = new STLExporter().parse(gltf.scene, { binary: true });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([data], { type: "model/stl" }));
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
  return data.byteLength;
}

export const stlName = (row, part) => `${row.model_short}-${row.task}-trial-${row.trial}-${part.id}`.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + ".stl";
