/* Isolated JavaScriptCore environment. No browser or network capabilities. */
var window = this;
globalThis.crypto = {
  getRandomValues: function (array) {
    if (!ArrayBuffer.isView(array) || array instanceof DataView ||
        array instanceof Float32Array || array instanceof Float64Array ||
        !Number.isSafeInteger(array.byteLength) || array.byteLength > 65536) throw new Error('randomUnavailable');
    var target = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
    var bytes = nativeSecureRandom(target.length);
    if (!bytes || bytes.length !== target.length) throw new Error('randomUnavailable');
    for (var i = 0; i < target.length; i++) {
      if (!Number.isInteger(bytes[i]) || bytes[i] < 0 || bytes[i] > 255) throw new Error('randomUnavailable');
      target[i] = bytes[i];
    }
    return array;
  }
};
Math.random = function () { throw new Error('insecureRandomForbidden'); };
