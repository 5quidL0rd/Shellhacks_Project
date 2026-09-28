// Recover an older cached HTML page after the current bundle changes.
if (!new URLSearchParams(location.search).has('_px_refresh')) {
  const separator = location.search ? '&' : '?'
  location.replace(`${location.pathname}${location.search}${separator}_px_refresh=${Date.now()}${location.hash}`)
}
