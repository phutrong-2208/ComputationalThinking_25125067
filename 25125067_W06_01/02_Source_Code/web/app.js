/* StudySpot: vanilla JS. All API/user text is inserted with textContent. */
"use strict";
const $ = (id) => document.getElementById(id);
const PRESETS = {hcm:[10.779783,106.699018],hanoi:[21.0285,105.8542],danang:[16.0612,108.2277],kontum:[14.3546,108.0084]};
const TYPE = {cafe:"Quán cà phê",library:"Thư viện"};
const state = {places:[],meta:null,tab:"explore",selected:null,map:null,circle:null,center:null,markers:new Map(),layer:null,busy:false,dirty:false,toastTimer:null};
let saved = new Map();
try {
  const items = JSON.parse(localStorage.getItem("studyspot.saved.v1") || "[]");
  if (Array.isArray(items)) for (const p of items.slice(0,100)) {
    if (p && /^(node|way|relation)\/\d+$/.test(p.id) && typeof p.name==="string" && Number.isFinite(p.lat) && Number.isFinite(p.lon) && Math.abs(p.lat)<=90 && Math.abs(p.lon)<=180 && TYPE[p.category]) saved.set(p.id,p);
  }
} catch { /* A disabled/corrupt storage must not prevent searching. */ }

function node(tag, text, className) {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function toast(message) {clearTimeout(state.toastTimer);$("toast").textContent=message;$("toast").hidden=false;state.toastTimer=setTimeout(()=>$("toast").hidden=true,3300);}
function distance(d) {return d<1000?`${d} m`:`${(d/1000).toFixed(2).replace(".",",")} km`;}
function status(message,error=false) {$("status").textContent=message;$("status").classList.toggle("error",error);}
function savePlace(p) {
  if(saved.has(p.id))saved.delete(p.id);else {
    if(saved.size>=100){toast("Bạn có thể lưu tối đa 100 địa điểm.");return;}
    saved.set(p.id,{...p,saved_at:new Date().toISOString()});
  }
  try {localStorage.setItem("studyspot.saved.v1",JSON.stringify([...saved.values()]));}
  catch {toast("Trình duyệt không cho lưu lâu dài; chỉ giữ trong phiên này.");}
  render();
  if(state.selected?.id===p.id)updateSaveButton();
}
function updateSaveButton() {$("detail-save").textContent=saved.has(state.selected.id)?"Bỏ lưu địa điểm":"Lưu địa điểm";}
function currentPlaces() {
  const needle=$("name-filter").value.trim().toLocaleLowerCase("vi");
  return (state.tab==="saved"?[...saved.values()]:state.places).filter(p=>(!needle||p.name.toLocaleLowerCase("vi").includes(needle))&&(!$("wifi-filter").checked||p.wifi==="yes")&&(!$("access-filter").checked||p.wheelchair==="yes"));
}
function render() {
  $("saved-count").textContent=saved.size;
  $("explore-tab").classList.toggle("active",state.tab==="explore");$("saved-tab").classList.toggle("active",state.tab==="saved");
  $("explore-tab").setAttribute("aria-pressed",state.tab==="explore");$("saved-tab").setAttribute("aria-pressed",state.tab==="saved");
  const places=currentPlaces();$("result-count").textContent=places.length;$("export-button").disabled=!places.length;
  const container=$("results");container.replaceChildren();
  if(!places.length) {
    const empty=node("div",undefined,"empty");
    const filteredSaved=state.tab==="saved"&&saved.size>0;
    empty.append(node("div","⌂","empty-art"),node("h3",filteredSaved?"Không có địa điểm khớp bộ lọc.":state.tab==="saved"?"Một góc nhỏ để nhớ.":state.meta?"Chưa tìm thấy địa điểm phù hợp.":"Góc học tập tiếp theo đang chờ bạn."),node("p",filteredSaved?"Thử bỏ bộ lọc hoặc thay đổi tên tìm kiếm.":state.tab==="saved"?"Bấm biểu tượng lưu bên cạnh một địa điểm.":state.meta?"Thử bỏ bộ lọc hoặc chọn bán kính lớn hơn.":"Chọn khu vực và nhấn Tìm địa điểm để khám phá."));container.append(empty);
  }
  for(const p of places) {
    const card=node("article",undefined,"place-card");card.dataset.id=p.id;
    const symbol=node("div",p.category==="cafe"?"☕":"▤",`place-symbol ${p.category}`);symbol.setAttribute("aria-hidden","true");
    const body=node("div"),h=node("h3"),open=node("button",p.name,"card-open");open.type="button";open.addEventListener("click",()=>showDetail(p));h.append(open);
    const dist=state.tab==="saved"?"Đã lưu trên trình duyệt":`${distance(p.distance_m)} · đường chim bay`;
    body.append(h,node("p",`${TYPE[p.category]} · ${dist}`,"card-meta"));
    if(p.wifi==="yes"||p.wheelchair==="yes")body.append(node("p",[p.wifi==="yes"?"Wi-Fi được ghi nhận":"",p.wheelchair==="yes"?"Có lối xe lăn":""].filter(Boolean).join(" · "),"card-tags"));
    const save=node("button",saved.has(p.id)?"▣":"▢",`save-button${saved.has(p.id)?" saved":""}`);save.type="button";save.setAttribute("aria-label",`${saved.has(p.id)?"Bỏ lưu":"Lưu"} ${p.name}`);save.setAttribute("aria-pressed",saved.has(p.id));save.addEventListener("click",()=>savePlace(p));
    card.append(symbol,body,save);container.append(card);
  }
  renderMarkers(places);
}
function showDetail(p) {
  state.selected=p;$("detail-title").textContent=p.name;$("detail-category").textContent=TYPE[p.category];
  $("detail-distance").textContent=state.tab==="saved"?"Địa điểm bạn đã lưu trên trình duyệt này.":`${distance(p.distance_m)} đường chim bay từ tâm truy vấn.`;
  const dl=$("detail-fields");dl.replaceChildren();
  const fields=[["ĐỊA CHỈ",p.address||"Chưa được cập nhật trên OSM"],["WI-FI",p.wifi==="yes"?"Có (theo thẻ OSM)":p.wifi==="no"?"Không (theo thẻ OSM)":"Chưa có thông tin"],["LỐI XE LĂN",({yes:"Có",no:"Không",limited:"Hạn chế"})[p.wheelchair]||"Chưa có thông tin"],["GIỜ MỞ CỬA (DỮ LIỆU GỐC)",p.opening_hours||"Chưa có thông tin"],["TỌA ĐỘ",`${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}`]];
  for(const [label,value] of fields)dl.append(node("dt",label),node("dd",value));
  $("detail-osm").href=`https://www.openstreetmap.org/${p.id}`;updateSaveButton();
  if(state.map){state.map.panTo([p.lat,p.lon]);state.markers.get(p.id)?.openPopup();}
  if(!$("detail-dialog").open)$("detail-dialog").showModal();
}
function renderMarkers(places) {
  if(!state.map)return;
  state.layer.clearLayers();state.markers.clear();
  for(const p of places){
    const symbol=p.category==="cafe"?"☕":"▤";
    const icon=L.divIcon({html:`<div class="marker-dot ${p.category}"><span>${symbol}</span></div>`,iconSize:[28,32],iconAnchor:[14,30],popupAnchor:[0,-25]});
    const marker=L.marker([p.lat,p.lon],{icon,title:p.name}).addTo(state.layer);
    const popup=node("div"),strong=node("strong",p.name),meta=node("div",TYPE[p.category]),button=node("button","Xem chi tiết");button.addEventListener("click",()=>showDetail(p));popup.append(strong,meta,button);marker.bindPopup(popup);state.markers.set(p.id,marker);
  }
}
function coordinates() {
  if(!$("lat").value.trim()||!$("lon").value.trim())throw new Error("Vui lòng nhập đủ vĩ độ và kinh độ.");
  const lat=Number($("lat").value),lon=Number($("lon").value);
  if(!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180)throw new Error("Tọa độ không hợp lệ.");
  return [lat,lon];
}
function previewCenter(move=true) {
  let coords;try{coords=coordinates();}catch{return;}
  state.dirty=!!state.meta;
  if(state.map){state.center.setLatLng(coords);if(move)state.map.setView(coords,15);}
  if(state.meta&&state.tab==="explore")status("Tâm hoặc tùy chọn đã thay đổi. Kết quả cũ vẫn giữ; nhấn Tìm địa điểm để cập nhật.");
}
function fitSearch() {
  if(!state.map)return;
  if(state.tab==="saved"&&state.markers.size){state.map.fitBounds(L.featureGroup([...state.markers.values()]).getBounds().pad(.2),{maxZoom:17});return;}
  if(state.circle&&!state.dirty)state.map.fitBounds(state.circle.getBounds(),{padding:[35,35]});
  else {try{state.map.setView(coordinates(),15);}catch{toast("Nhập tọa độ hợp lệ trước.");}}
}
async function search(event) {
  event?.preventDefault();if(state.busy)return;
  let coords;try{coords=coordinates();}catch(e){status(e.message,true);return;}
  state.busy=true;$("search-button").disabled=true;$("search-button").querySelector("span").textContent="Đang tìm trên OSM…";
  status("Đang kết nối API OpenStreetMap. Truy vấn có thể mất đến 40 giây.");
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),45000);
  const query=new URLSearchParams({lat:coords[0],lon:coords[1],radius:$("radius").value,category:$("category").value});
  try {
    const response=await fetch(`/api/places?${query}`,{signal:controller.signal});
    const result=await response.json();if(!response.ok)throw new Error(result.error||`Lỗi HTTP ${response.status}`);
    state.places=result.places;state.meta=result.meta;state.tab="explore";
    // Restore the exact inputs that produced these results if changed mid-request.
    $("lat").value=coords[0];$("lon").value=coords[1];$("radius").value=result.meta.radius_m;$("category").value=result.meta.category;
    const preset=Object.entries(PRESETS).find(([,v])=>v[0]===coords[0]&&v[1]===coords[1]);$("area").value=preset?.[0]||"custom";
    state.dirty=false;$("name-filter").value="";$("wifi-filter").checked=false;$("access-filter").checked=false;
    if(state.map){state.center.setLatLng(coords);state.circle?.remove();state.circle=L.circle(coords,{radius:result.meta.radius_m,color:"#6659cf",weight:1.5,dashArray:"5 6",fillColor:"#a69be0",fillOpacity:.08}).addTo(state.map);}
    render();fitSearch();
    const time=new Date(result.meta.fetched_at).toLocaleTimeString("vi-VN",{hour:"2-digit",minute:"2-digit"});
    status(`${result.places.length} địa điểm · ${result.meta.cached?"bản lưu đệm":"dữ liệu từ API"} lúc ${time}.${result.meta.truncated?" Tập kết quả bị giới hạn, có thể chưa đầy đủ.":" Dữ liệu cộng đồng có thể chưa đầy đủ."}`);
    $("api-info").textContent=JSON.stringify({source:result.meta.source,endpoint:result.meta.endpoint,query:result.meta.query,fetched_at:result.meta.fetched_at,osm_base:result.meta.osm_base,cached:result.meta.cached,returned_count:result.meta.returned_count},null,2);
  } catch(error) {
    status(`${error.name==="AbortError"?"Truy vấn hết thời gian chờ.":error.message} ${state.meta?"Kết quả trước đó được giữ nguyên.":"Chưa có kết quả mới."}`,true);
  } finally {
    clearTimeout(timeout);state.busy=false;$("search-button").disabled=false;$("search-button").querySelector("span").textContent="Tìm địa điểm";
  }
}
function exportPlaces() {
  const places=currentPlaces();if(!places.length)return;
  const collection=buildGeoJSON(places,state.meta,state.tab==="saved");
  const url=URL.createObjectURL(new Blob([JSON.stringify(collection,null,2)],{type:"application/geo+json"}));
  const link=node("a");link.href=url;link.download="studyspot-places.geojson";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast("Đã xuất các địa điểm đang hiển thị.");
}
async function initMap() {
  try {
    if(typeof L==="undefined")throw new Error("Không tải được thư viện bản đồ.");
    const response=await fetch("/api/config");if(!response.ok)throw new Error("Không tải được cấu hình bản đồ.");const config=await response.json();
    for(const option of [...$("radius").options])if(Number(option.value)>config.max_radius)option.remove();
    state.map=L.map("map",{zoomControl:false,scrollWheelZoom:true}).setView(PRESETS.hcm,15);
    L.control.zoom({position:"topright"}).addTo(state.map);
    const tile=L.tileLayer(config.tile_url,{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(state.map);
    tile.on("tileerror",()=>{$("map-alert").hidden=false;$("map-alert").textContent="Một số ô bản đồ chưa tải được. Danh sách địa điểm vẫn dùng được.";});
    state.layer=L.layerGroup().addTo(state.map);
    state.center=L.marker(PRESETS.hcm,{icon:L.divIcon({html:'<div class="center-pin"></div>',iconSize:[15,15],iconAnchor:[7,7]}),interactive:false}).addTo(state.map);
    state.map.on("click",event=>{$("lat").value=event.latlng.lat.toFixed(6);$("lon").value=event.latlng.lng.toFixed(6);$("area").value="custom";previewCenter(false);});
    render();
  } catch(error) {$("map-alert").hidden=false;$("map-alert").textContent=`${error.message} Bạn vẫn có thể tìm bằng tọa độ và xem danh sách.`;}
}
$("search-form").addEventListener("submit",search);
$("area").addEventListener("change",()=>{const p=PRESETS[$("area").value];if(p){$("lat").value=p[0];$("lon").value=p[1];previewCenter();}});
for(const id of ["lat","lon"])$(id).addEventListener("change",()=>{$("area").value="custom";previewCenter();});
for(const id of ["radius","category"])$(id).addEventListener("change",()=>{state.dirty=!!state.meta;if(state.meta)status("Tùy chọn đã thay đổi. Nhấn Tìm địa điểm để cập nhật kết quả.");});
for(const id of ["name-filter","wifi-filter","access-filter"])$(id).addEventListener("input",render);
$("explore-tab").addEventListener("click",()=>{state.tab="explore";render();status(state.meta?`${state.places.length} địa điểm từ truy vấn gần nhất. Bộ lọc chỉ áp dụng trên kết quả này.`:"Chọn khu vực và nhấn Tìm địa điểm để bắt đầu.");});
$("saved-tab").addEventListener("click",()=>{state.tab="saved";render();status("Địa điểm lưu trên trình duyệt; không truy vấn lại API. Khoảng cách gốc xem trong GeoJSON.");fitSearch();});
$("detail-save").addEventListener("click",()=>savePlace(state.selected));
$("detail-close").addEventListener("click",()=>$("detail-dialog").close());
$("about-button").addEventListener("click",()=>$("about-dialog").showModal());
$("about-close").addEventListener("click",()=>$("about-dialog").close());
$("fit-button").addEventListener("click",fitSearch);$("export-button").addEventListener("click",exportPlaces);
render();initMap();
