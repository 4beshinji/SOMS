import { useState, useEffect, useRef } from 'react';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';
import type { AvatarModel } from '../components/avatar/types';
import { VrmAdapter } from '../components/avatar/VrmAdapter';

export type { AvatarModel } from '../components/avatar/types';

type AvatarFormat = 'vrm' | 'mmd' | 'unknown';

function detectFormat(url: string): AvatarFormat {
  const lower = url.toLowerCase();
  if (lower.endsWith('.vrm')) return 'vrm';
  if (lower.endsWith('.pmd') || lower.endsWith('.pmx')) return 'mmd';
  return 'unknown';
}

export function useAvatarLoader(url: string | null): {
  model: AvatarModel | null;
  loading: boolean;
  error: string | null;
} {
  const [model, setModel] = useState<AvatarModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prevUrl = useRef<string | null>(null);

  useEffect(() => {
    if (!url || url === prevUrl.current) return;
    prevUrl.current = url;

    model?.dispose();
    setModel(null);
    setLoading(true);
    setError(null);

    const format = detectFormat(url);
    console.log('[AvatarLoader] Loading:', url, 'format:', format);

    if (format === 'unknown') {
      setError(`Unsupported format: ${url}`);
      setLoading(false);
      return;
    }

    const loader = format === 'vrm' ? loadVrm(url) : loadMmd(url);
    loader
      .then((m) => {
        console.log('[AvatarLoader] Loaded successfully:', format);
        setModel(m);
      })
      .catch((e) => {
        console.error('[AvatarLoader] Load failed:', e);
        setError(e.message || String(e));
      })
      .finally(() => setLoading(false));
  }, [url]);

  return { model, loading, error };
}

async function loadVrm(url: string): Promise<AvatarModel> {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const gltf = await loader.loadAsync(url);
  const vrm = gltf.userData.vrm;
  if (!vrm) throw new Error('VRM data not found in GLTF');
  vrm.scene.rotation.y = Math.PI;
  return new VrmAdapter(vrm);
}

async function loadMmd(url: string): Promise<AvatarModel> {
  const { MMDLoader } = await import('three-stdlib');
  const { MmdAdapter } = await import('../components/avatar/MmdAdapter');

  const lastSlash = url.lastIndexOf('/');
  const resourcePath = lastSlash >= 0 ? url.substring(0, lastSlash + 1) : './';

  return new Promise((resolve, reject) => {
    const loader = new MMDLoader();
    loader.setResourcePath(resourcePath);
    loader.load(
      url,
      (mesh: any) => {
        console.log('[MMDLoader] Loaded mesh:', mesh?.geometry?.attributes?.position?.count, 'vertices');
        resolve(new MmdAdapter(mesh));
      },
      undefined,
      (err: any) => reject(new Error(`MMD load failed: ${err}`)),
    );
  });
}
