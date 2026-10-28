import forge from 'node-forge';
import { importP12 } from './certificate-recovery.js';
self.onmessage = async ({ data }) => {
  try {
    const identity = await importP12(data.file, data.password, data.teamId);
    self.postMessage({ privateKeyPem: forge.pki.privateKeyToPem(identity.keys.privateKey), teamId: identity.teamId, certificateDerBase64: identity.certificateDerBase64 });
  } catch { self.postMessage({ error: 'P12 密碼、私鑰、有效憑證或 Team 不符，或檔案超過安全解析限制' }); }
};
