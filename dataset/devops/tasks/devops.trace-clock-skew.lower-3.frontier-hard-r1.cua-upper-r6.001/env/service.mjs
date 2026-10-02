import { startTraceService } from "../repo/verifiers/trace_service.mjs";

function options(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--host") result.host = argv[++index];
    else if (argv[index] === "--port") result.port = Number(argv[++index]);
    else if (argv[index] === "--profile") result.profile = argv[++index];
  }
  return result;
}

startTraceService(options(process.argv.slice(2))).then(({ address }) => {
  process.stdout.write(`trace query service on http://${address.address}:${address.port}\n`);
});
