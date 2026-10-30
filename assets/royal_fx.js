/* Royal Constellation — efeito WebGL leve, opcional, sem bibliotecas externas. */
(() => {
  const canvas = document.getElementById('royal-constellation');
  if (!canvas || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const gl = canvas.getContext('webgl', {alpha:true, antialias:false, powerPreference:'low-power', preserveDrawingBuffer:false});
  if (!gl) return; // CSS segue funcionando em navegadores sem WebGL.
  const vertex = `attribute vec3 position;uniform float time;uniform vec2 pointer;varying float lum;void main(){vec3 p=position;p.xy+=pointer*0.15*(1.0-p.z);p.x+=sin(time*0.09+p.z*12.0)*0.045;float depth=1.7-p.z;gl_Position=vec4(p.xy/depth,p.z*0.1,1.0);gl_PointSize=(2.2+3.1*p.z)/depth;lum=0.4+0.6*p.z;}`;
  const fragment = `precision mediump float;varying float lum;void main(){float d=length(gl_PointCoord-vec2(0.5));float a=smoothstep(0.5,0.0,d)*lum*0.7;gl_FragColor=vec4(0.98,0.72,0.36,a);}`;
  function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);return gl.getShaderParameter(s,gl.COMPILE_STATUS)?s:null;}
  const v=shader(gl.VERTEX_SHADER,vertex),f=shader(gl.FRAGMENT_SHADER,fragment);if(!v||!f)return;
  const program=gl.createProgram();gl.attachShader(program,v);gl.attachShader(program,f);gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))return;
  const count=matchMedia('(max-width: 760px)').matches?75:175;
  const points=new Float32Array(count*3);for(let i=0;i<count;i++){points[i*3]=Math.random()*3.6-1.8;points[i*3+1]=Math.random()*2.2-1.1;points[i*3+2]=Math.random();}
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,points,gl.STATIC_DRAW);gl.useProgram(program);
  const position=gl.getAttribLocation(program,'position'),time=gl.getUniformLocation(program,'time'),pointer=gl.getUniformLocation(program,'pointer');gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,3,gl.FLOAT,false,0,0);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);
  let active=true,request=0;const move={x:0,y:0};
  canvas.parentElement.addEventListener('pointermove',e=>{const b=canvas.getBoundingClientRect();move.x=(e.clientX-b.left)/b.width-.5;move.y=.5-(e.clientY-b.top)/b.height;},{passive:true});
  const observer=new IntersectionObserver(entries=>{active=entries.some(e=>e.isIntersecting);if(active&&!request)request=requestAnimationFrame(draw);});observer.observe(canvas);
  document.addEventListener('visibilitychange',()=>{active=!document.hidden;if(active&&!request)request=requestAnimationFrame(draw);});
  function draw(t){request=0;if(!active)return;const ratio=Math.min(devicePixelRatio||1,1.5),w=Math.floor(canvas.clientWidth*ratio),h=Math.floor(canvas.clientHeight*ratio);if(w<1||h<1)return;if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.uniform1f(time,t/1000);gl.uniform2f(pointer,move.x,move.y);gl.drawArrays(gl.POINTS,0,count);request=requestAnimationFrame(draw);}
  request=requestAnimationFrame(draw);
})();
