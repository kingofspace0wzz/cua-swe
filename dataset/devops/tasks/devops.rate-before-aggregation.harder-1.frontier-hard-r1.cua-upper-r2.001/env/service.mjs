import {startCounterService} from "../repo/verifiers/counter_service.mjs";

const options = {};
for (let index = 2; index < process.argv.length; index += 1) {
  if (process.argv[index] === "--host") options.host = process.argv[++index];
  else if (process.argv[index] === "--port") options.port = Number(process.argv[++index]);
  else if (process.argv[index] === "--profile") options.profile = process.argv[++index];
}
startCounterService(options).then(({address}) => {
  process.stdout.write(`counter service on http://${address.address}:${address.port}\n`);
});
