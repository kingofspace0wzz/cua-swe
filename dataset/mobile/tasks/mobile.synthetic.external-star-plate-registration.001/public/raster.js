// Generic input adapter: component centers come ONLY from imported PNG pixels.
// The product uses navy stars, magenta rings, and light grid/paper. No OCR/pose solver.
export async function readPlate(url) {
  const image=new Image();image.src=url;await image.decode();
  const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
  const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0);
  const {data,width:w,height:h}=context.getImageData(0,0,canvas.width,canvas.height);
  function components(kind){
    const mask=new Uint8Array(w*h),out=[];
    for(let i=0;i<mask.length;i++){const r=data[i*4],g=data[i*4+1],b=data[i*4+2];mask[i]=kind==='star'?(r<70&&g<80&&b<95):(r>120&&r<220&&g<80&&b>80&&b<160);}
    for(let i=0;i<mask.length;i++)if(mask[i]){
      const todo=[i];mask[i]=0;let n=0,sx=0,sy=0,minX=w,minY=h,maxX=0,maxY=0;
      while(todo.length){const k=todo.pop(),x=k%w,y=Math.floor(k/w);n++;sx+=x;sy+=y;minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);
        for(const [xx,yy] of [[x-1,y],[x+1,y],[x,y-1],[x,y+1]])if(xx>=0&&xx<w&&yy>=0&&yy<h&&mask[yy*w+xx]){mask[yy*w+xx]=0;todo.push(yy*w+xx);}}
      if(n>=40&&maxX-minX>=7&&maxY-minY>=7)out.push({x:sx/n,y:sy/n,radius:(maxX-minX+maxY-minY)/4});
    }
    return out.sort((a,b)=>a.y-b.y||a.x-b.x).map((p,i)=>({...p,id:(kind==='star'?'P':'T')+String(i+1).padStart(2,'0')}));
  }
  return {points:components('star'),targets:components('target')};
}
