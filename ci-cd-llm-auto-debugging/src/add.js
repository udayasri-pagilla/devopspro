export function add(a, b) {
  return a + b;
}

// Simple CLI for manual testing
if (process.argv[1] && process.argv[1].endsWith('add.js') && import.meta.url.startsWith('file:')) {
  const [,, x, y] = process.argv;
  const a = Number(x || 0);
  const b = Number(y || 0);
  console.log(add(a, b));
}
