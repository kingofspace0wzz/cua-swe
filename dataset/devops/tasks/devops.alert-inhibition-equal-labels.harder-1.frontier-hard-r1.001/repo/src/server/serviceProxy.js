import { request as httpRequest } from "node:http";

export function serviceOrigin(environment) {
  const value = environment.CUA_SWE_EXTERNAL_SERVICE_ORIGIN;
  if (!value) throw new Error("CUA_SWE_EXTERNAL_SERVICE_ORIGIN is required");
  return new URL(value);
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks)));
    request.on("error", reject);
  });
}

export function createServiceProxy(origin) {
  return async function forward(incoming, pathname, search) {
    const body = await readBody(incoming);
    return new Promise((resolve, reject) => {
      const request = httpRequest(
        new URL(`${pathname}${search}`, origin),
        {
          method: incoming.method,
          headers: {
            "content-type":
              incoming.headers["content-type"] || "application/json",
            "content-length": body.length,
          },
        },
        (response) => {
          const chunks = [];
          response.on("data", (chunk) => chunks.push(chunk));
          response.on("end", () => {
            resolve({
              status: response.statusCode || 500,
              type:
                response.headers["content-type"]
                || "application/json; charset=utf-8",
              body: Buffer.concat(chunks),
            });
          });
        },
      );
      request.on("error", reject);
      if (body.length) request.write(body);
      request.end();
    });
  };
}
