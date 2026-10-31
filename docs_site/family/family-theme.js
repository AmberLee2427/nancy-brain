(()=>{const key='rges-family-theme';function apply(mode){const r=document.documentElement;r.dataset.familyTheme=mode;r.dataset.theme=mode;r.classList.toggle('dark',mode==='dark');window.dispatchEvent(new CustomEvent('family-theme-change',{detail:mode}));const b=document.body;if(b){b.setAttribute('data-md-color-scheme',mode==='dark'?'slate':'default');const t=document.querySelector('.family-toggle');if(t){t.textContent=mode==='dark'?'☀ Light mode':'☾ Dark mode';t.setAttribute('aria-label','Switch color theme');}}}let mode=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';try{mode=localStorage.getItem(key)||mode}catch{}apply(mode);document.addEventListener('DOMContentLoaded',()=>{const button=document.createElement('button');button.className='family-toggle';button.type='button';button.addEventListener('click',()=>{mode=document.documentElement.dataset.familyTheme==='dark'?'light':'dark';apply(mode);try{localStorage.setItem(key,mode)}catch{}});document.body.append(button);apply(mode);});})();
// GraphicWalker's open shadow roots need their own geometry rule.
(()=>{function init(){if(!document.body.classList.contains('family-mldb'))return;
 const watched=new WeakSet();let timer;
 const observer=new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(scan,50)});
 function visit(root){if(!watched.has(root)){watched.add(root);observer.observe(root,{childList:true,subtree:true})}
  for(const node of root.querySelectorAll('*')){const shadow=node.shadowRoot;if(!shadow)continue;
   if(!shadow.querySelector('style[data-family-geometry]')){const style=document.createElement('style');style.dataset.familyGeometry='';style.textContent=':host{--radius:0px}*,*::before,*::after{border-radius:0!important}';shadow.append(style)}
   visit(shadow);
  }
 }
 function scan(){visit(document)}
 scan();requestAnimationFrame(()=>requestAnimationFrame(scan));
 }if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();})();
