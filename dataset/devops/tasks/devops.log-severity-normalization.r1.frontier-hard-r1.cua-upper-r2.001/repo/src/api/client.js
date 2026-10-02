export async function api(path,data) {
 const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'content-type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
 if(!response.ok) throw new Error('Receiver request failed: '+response.status);
 return response.json();
}
