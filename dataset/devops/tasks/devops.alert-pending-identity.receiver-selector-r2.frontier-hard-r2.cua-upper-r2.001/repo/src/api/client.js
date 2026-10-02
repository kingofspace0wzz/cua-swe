export async function request(path, body) {
 const response = await fetch('/api/' + path, body === undefined ? {} : {
  method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body),
 });
 if(!response.ok)throw new Error('Evaluator request failed: ' + response.status);
 return response.json();
}
