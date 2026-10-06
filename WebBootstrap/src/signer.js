export function signLocally(inputs, { signal, onPhase } = {}) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('sign-worker.js', document.baseURI));
    const timer = setTimeout(() => finish(new Error('Signing timed out after five minutes. No output was retained.')), 5 * 60 * 1000);
    const aborted = () => finish(new DOMException('Signing cancelled', 'AbortError'));
    let settled = false;
    function finish(error, bytes) {
      if (settled) return; settled = true;
      clearTimeout(timer); signal?.removeEventListener('abort', aborted); worker.terminate();
      if (error) reject(error); else resolve(new Blob([bytes], { type: 'application/octet-stream' }));
    }
    signal?.addEventListener('abort', aborted, { once: true });
    worker.onmessage = ({ data }) => {
      if (data.phase === 'done') finish(null, data.bytes);
      else if (data.phase === 'error') finish(new Error(data.message));
      else onPhase?.(data.phase);
    };
    worker.onerror = () => finish(new Error('The signing worker could not run. This browser may have exhausted its memory.'));
    if (signal?.aborted) aborted(); else worker.postMessage(inputs);
  });
}
