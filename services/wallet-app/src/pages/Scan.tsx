import { useRef, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import jsQR from 'jsqr';
import { claimTaskReward } from '../api/wallet';

interface ScanProps {
  userId: number;
}

interface QRPayload {
  task_id: number;
  amount: number;
}

function parseQR(text: string): QRPayload | null {
  try {
    const url = new URL(text);
    if (url.protocol !== 'soms:' || url.hostname !== 'reward') return null;
    const taskId = parseInt(url.searchParams.get('task_id') || '', 10);
    const amount = parseInt(url.searchParams.get('amount') || '', 10);
    if (isNaN(taskId) || isNaN(amount)) return null;
    return { task_id: taskId, amount };
  } catch {
    return null;
  }
}

export default function Scan({ userId }: ScanProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState<'idle' | 'scanning' | 'claiming' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [claimedAmount, setClaimedAmount] = useState(0);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const navigate = useNavigate();

  const startCamera = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError(
        window.isSecureContext
          ? 'このブラウザではカメラAPIを利用できません。'
          : 'カメラにはHTTPSが必要です。https://...:8443 でアクセスしてください。',
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setStatus('scanning');
      setCameraError(null);
    } catch {
      setCameraError(
        window.isSecureContext
          ? 'カメラへのアクセスが拒否されました。カメラの許可を確認してください。'
          : 'カメラにはHTTPSが必要です。https://...:8443 でアクセスしてください。',
      );
    }
  }, []);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    startCamera();
    return stopCamera;
  }, [startCamera, stopCamera]);

  const handleDetected = useCallback(async (payload: QRPayload) => {
    stopCamera();
    setStatus('claiming');
    setClaimedAmount(payload.amount);
    setMessage(`${payload.amount} SOMS を受け取り中...`);
    try {
      await claimTaskReward(userId, payload.task_id, payload.amount);
      setStatus('success');
      setMessage(`+${payload.amount} SOMS`);
    } catch (e) {
      setStatus('error');
      setMessage(e instanceof Error ? e.message : '受け取りに失敗しました');
    }
  }, [userId, stopCamera]);

  useEffect(() => {
    if (status !== 'scanning') return;

    let running = true;

    const hasBarcodeDetector = 'BarcodeDetector' in window;
    const detector = hasBarcodeDetector
      ? new (window as unknown as { BarcodeDetector: new (opts: { formats: string[] }) => { detect: (src: HTMLVideoElement) => Promise<{ rawValue: string }[]> } }).BarcodeDetector({ formats: ['qr_code'] })
      : null;

    async function scanFrame(): Promise<string | null> {
      if (!videoRef.current) return null;

      if (detector) {
        const barcodes = await detector.detect(videoRef.current);
        if (barcodes.length > 0) return barcodes[0].rawValue;
        return null;
      }

      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!canvas || video.readyState < video.HAVE_ENOUGH_DATA) return null;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const code = jsQR(imageData.data, imageData.width, imageData.height);
      return code?.data ?? null;
    }

    async function scan() {
      while (running && videoRef.current) {
        try {
          const data = await scanFrame();
          if (data) {
            const payload = parseQR(data);
            if (payload) {
              running = false;
              handleDetected(payload);
              return;
            }
          }
        } catch { /* ignore detect errors */ }
        await new Promise(r => setTimeout(r, 300));
      }
    }

    scan();
    return () => { running = false; };
  }, [status, handleDetected]);

  useEffect(() => {
    if (status !== 'success') return;
    const timer = setTimeout(() => navigate('/'), 3000);
    return () => clearTimeout(timer);
  }, [status, navigate]);

  const handleReset = () => {
    setStatus('idle');
    setMessage('');
    setClaimedAmount(0);
    startCamera();
  };

  return (
    <div className="p-4 pb-24 space-y-4">
      <h1 className="text-xl font-bold text-[var(--gray-900)]">QR スキャン</h1>
      <p className="text-sm text-[var(--gray-500)]">タスクのQRコードを読み取って報酬を受け取ります。</p>

      {status !== 'success' && (
        <div className="relative rounded-2xl overflow-hidden bg-[var(--gray-900)] aspect-square">
          <video ref={videoRef} className="w-full h-full object-cover" playsInline muted />
          <canvas ref={canvasRef} className="hidden" />
          {status === 'scanning' && (
            <div className="absolute inset-0 border-2 border-[var(--primary-500)]/50 rounded-2xl pointer-events-none">
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 border-2 border-[var(--primary-500)] rounded-lg" />
            </div>
          )}
          {status === 'claiming' && (
            <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
              <div className="w-12 h-12 border-4 border-[var(--primary-500)] border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
      )}

      {status === 'success' && (
        <div className="flex flex-col items-center justify-center py-12 space-y-6 animate-fade-in">
          <div className="relative w-28 h-28">
            <svg viewBox="0 0 100 100" className="w-full h-full">
              <circle
                cx="50" cy="50" r="45"
                fill="none" stroke="#4CAF50" strokeWidth="4"
                className="animate-draw-circle"
              />
              <path
                d="M30 52 L44 66 L72 38"
                fill="none" stroke="#4CAF50" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"
                className="animate-draw-check"
              />
            </svg>
          </div>

          <div className="text-center">
            <p className="text-5xl font-bold text-[var(--gold-dark)]">
              +{claimedAmount}
            </p>
            <p className="text-lg text-[var(--gray-500)] mt-1">SOMS</p>
          </div>

          <p className="text-sm text-[var(--gray-500)]">3秒後にホームに戻ります...</p>
        </div>
      )}

      {cameraError && (
        <div className="bg-[var(--error-50)] border border-[var(--error-500)] rounded-lg p-3 text-sm text-[var(--error-700)]">
          {cameraError}
        </div>
      )}

      {message && status === 'error' && (
        <div className="bg-[var(--error-50)] border border-[var(--error-500)] rounded-lg p-3 text-sm text-[var(--error-700)]">
          {message}
        </div>
      )}

      {(status === 'success' || status === 'error') && (
        <button
          onClick={status === 'success' ? () => navigate('/') : handleReset}
          className="w-full py-3 bg-[var(--primary-500)] text-white font-semibold rounded-xl cursor-pointer"
        >
          {status === 'success' ? 'ホームに戻る' : 'もう一度スキャン'}
        </button>
      )}

      <style>{`
        @keyframes fade-in {
          from { opacity: 0; transform: scale(0.9); }
          to { opacity: 1; transform: scale(1); }
        }
        .animate-fade-in {
          animation: fade-in 0.4s ease-out;
        }
        @keyframes draw-circle {
          from { stroke-dasharray: 283; stroke-dashoffset: 283; }
          to { stroke-dasharray: 283; stroke-dashoffset: 0; }
        }
        .animate-draw-circle {
          animation: draw-circle 0.6s ease-out forwards;
        }
        @keyframes draw-check {
          from { stroke-dasharray: 80; stroke-dashoffset: 80; }
          to { stroke-dasharray: 80; stroke-dashoffset: 0; }
        }
        .animate-draw-check {
          animation: draw-check 0.4s ease-out 0.4s forwards;
          stroke-dasharray: 80;
          stroke-dashoffset: 80;
        }
      `}</style>
    </div>
  );
}
