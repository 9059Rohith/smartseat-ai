export function pathsFor(base='/') {
  if(!/^\/(?:[a-zA-Z0-9_-]+\/)*$/.test(base))throw new Error('Invalid application base path')
  return {app:base,api:path=>base+'api'+(path.startsWith('/')?path:'/'+path),asset:path=>base+path.replace(/^\//,'')}
}
const paths=pathsFor(import.meta.env?.BASE_URL||'/')
export const apiURL=paths.api,assetURL=paths.asset,appHome=paths.app
export const hostedGateway=Boolean(import.meta.env?.VITE_SMARTSEAT_GATEWAY)||!['127.0.0.1','localhost'].includes(globalThis.location?.hostname||'localhost')
