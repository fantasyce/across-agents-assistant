const checklist = Object.freeze([
  "A readable project manifest exists",
  "A clear open-source license exists",
  "The first mission remains read-only"
]);

if (import.meta.url === `file://${process.argv[1]}`) {
  process.stdout.write(`${JSON.stringify({ status: "ready", checklist })}\n`);
}

export { checklist };
