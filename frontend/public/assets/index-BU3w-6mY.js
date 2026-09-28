// Recover visitors whose browser kept an older app shell after a deployment.
if (!new URLSearchParams(location.search).has('_px_refresh')) {
  const separator = location.search ? '&' : '?'
  location.replace(`${location.pathname}${location.search}${separator}_px_refresh=${Date.now()}${location.hash}`)
}
