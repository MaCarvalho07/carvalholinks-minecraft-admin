import { world, system } from '@minecraft/server';
// Read-only bridge: no network permission, player changes, or chat interception.
function item(stack,slot){
 if(!stack)return null;
 const data={slot,type:stack.typeId,amount:stack.amount};
 if(stack.nameTag)data.name=stack.nameTag;
 try{const d=stack.getComponent('minecraft:durability');if(d)data.durability={remaining:d.maxDurability-d.damage,max:d.maxDurability};}catch{}
 try{const e=stack.getComponent('minecraft:enchantable');if(e)data.enchantments=e.getEnchantments().map(x=>({type:x.type.id,level:x.level}));}catch{}
 return data;
}
function attribute(p,id){try{const c=p.getComponent(id);return c?{current:Math.round(c.currentValue*10)/10,max:c.effectiveMax}:null;}catch{return null;}}
function read(p){
 const data={name:p.name,health:attribute(p,'minecraft:health'),hunger:attribute(p,'minecraft:player.hunger'),inventory:[],equipment:[]};
 try{
  data.dimension=p.dimension.id;const l=p.location;data.position={x:Math.floor(l.x),y:Math.floor(l.y),z:Math.floor(l.z)};data.gamemode=p.getGameMode();
  const c=p.getComponent('minecraft:inventory')?.container;
  if(c)for(let i=0;i<Math.min(c.size,36);i++){const v=item(c.getItem(i),i);if(v)data.inventory.push(v);}
  const eq=p.getComponent('minecraft:equippable');
  if(eq)for(const slot of ['Head','Chest','Legs','Feet','Mainhand','Offhand']){const v=item(eq.getEquipment(slot),slot);if(v)data.equipment.push(v);}
 }catch(e){data.error=String(e).slice(0,180);}
 return data;
}
let previousSample=null;
system.runInterval(()=>{
 try{
  const at=Date.now(),tick=system.currentTick;
  const tickHealth=previousSample&&at>previousSample.at?{tps:Math.round(Math.min(20,(tick-previousSample.tick)*1000/(at-previousSample.at))*10)/10,sampleMs:at-previousSample.at}:null;
  previousSample={at,tick};
  console.warn('[CARV_ADMIN_V1]'+JSON.stringify({schema:1,at,tickHealth,players:world.getAllPlayers().slice(0,10).map(read)}));
 }
 catch(e){console.warn('[CARV_ADMIN_ERROR]'+String(e).slice(0,180));}
},200);
