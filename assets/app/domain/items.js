/** Shared item and filter semantics for the library, practice and export pages. */
import { itemsNow } from './data.js';
export const itemsOf = data => (Array.isArray(data?.items) ? data.items : []);
function asNumber(value,fallback=0){const n=Number(value);return Number.isFinite(n)?n:fallback}
function getItems(){return [...itemsNow()]}
function getItemByUid(uid){return getItems().find(item=>item.uid===uid)||null}
function clampNumber(value,min,max,fallback=0){const n=asNumber(value,fallback);return Math.max(min,Math.min(max,n))}
function parseReviewDate(value){if(!value)return null;const text=String(value).trim();const parts=text.includes('/')?text.split('/'):text.split('-');if(parts.length!==3)return null;const y=Number(parts[0]),m=Number(parts[1]),d=Number(parts[2]);if(!Number.isInteger(y)||!Number.isInteger(m)||!Number.isInteger(d))return null;const date=new Date(y,m-1,d);return date.getFullYear()===y&&date.getMonth()===m-1&&date.getDate()===d?date:null}
function daysSinceReview(value,fallback=30){const date=parseReviewDate(value);if(!date)return fallback;const today=new Date();const todayUtc=Date.UTC(today.getFullYear(),today.getMonth(),today.getDate());const dateUtc=Date.UTC(date.getFullYear(),date.getMonth(),date.getDate());return Math.max(0,Math.floor((todayUtc-dateUtc)/86400000))}
function decayMastery(mastery,days){const m=clampNumber(mastery,0,1,0);const d=Math.max(0,Math.floor(asNumber(days,0)));return m<=0?0:m*Math.exp(-d/(m*30+5))}
function isKilledItem(item){return asNumber(item.mastery,0)>=1||(item.tag||'').includes('已击杀')}
function scoreScheduleCandidate(item){const mastery=clampNumber(item.mastery,0,1,0);const difficulty=clampNumber(item.difficulty,1,10,5);const days=daysSinceReview(item.last_review,30);const decayed=decayMastery(mastery,days);let priority=(1-decayed)*(difficulty/10)+(days/60)*.3;if((item.tag||'').includes('待攻克')&&mastery<.3)priority+=.5;return{item,priority,days,decayed}}
function getDueDays(item){const dueDate=item.due_date;if(!dueDate)return null;const d=parseReviewDate(dueDate);if(!d)return null;const today=new Date();const todayUtc=Date.UTC(today.getFullYear(),today.getMonth(),today.getDate());const dueUtc=Date.UTC(d.getFullYear(),d.getMonth(),d.getDate());return Math.floor((dueUtc-todayUtc)/86400000)}
export function filterItems(items,filters){let result=[...items];if(filters.suspended!=='all'&&filters.suspended!=='suspended')result=result.filter(item=>!item.suspended);else if(filters.suspended==='suspended')result=result.filter(item=>item.suspended);if(filters.text){result=result.filter(item=>[item.uid,item.subject,item.category,item.tag,...(item.knowledge_tags||[]),...(item.labels||[])].join(' ').toLowerCase().includes(filters.text))}if(filters.subject)result=result.filter(item=>item.subject===filters.subject);if(filters.category)result=result.filter(item=>item.category===filters.category);if(filters.tag)result=result.filter(item=>(item.tag||'').includes(filters.tag));if(filters.knowledgeTag)result=result.filter(item=>(item.knowledge_tags||[]).includes(filters.knowledgeTag));if(filters.labels?.length){result=result.filter(item=>{const values=new Set(item.labels||[]);return filters.labelMode==='all'?filters.labels.every(label=>values.has(label)):filters.labels.some(label=>values.has(label))})}result=result.filter(item=>asNumber(item.difficulty,0)>=filters.difficultyMin&&asNumber(item.difficulty,0)<=(filters.difficultyMax||10));if(filters.masteryMin!=null)result=result.filter(item=>asNumber(item.mastery,0)>=filters.masteryMin);if(filters.masteryMax!=null)result=result.filter(item=>asNumber(item.mastery,0)<=filters.masteryMax);if(filters.dueFilter){result=result.filter(item=>{const dueDays=getDueDays(item);if(dueDays===null)return false;switch(filters.dueFilter){case'overdue':return dueDays<0;case'today':return dueDays===0;case'3days':return dueDays>=0&&dueDays<=3;case'7days':return dueDays>=0&&dueDays<=7;case'future':return dueDays>0;default:return true}})}switch(filters.sort){case'mastery-desc':result.sort((a,b)=>asNumber(b.mastery,0)-asNumber(a.mastery,0));break;case'diff-desc':result.sort((a,b)=>asNumber(b.difficulty,0)-asNumber(a.difficulty,0));break;case'diff-asc':result.sort((a,b)=>asNumber(a.difficulty,0)-asNumber(b.difficulty,0));break;case'date-desc':result.sort((a,b)=>(b.last_review||'').localeCompare(a.last_review||''));break;case'due-asc':result.sort((a,b)=>(getDueDays(a)??999)-(getDueDays(b)??999));break;case'due-desc':result.sort((a,b)=>(getDueDays(b)??-999)-(getDueDays(a)??-999));break;default:result.sort((a,b)=>asNumber(a.mastery,0)-asNumber(b.mastery,0))}return result}


export const allItems = getItems;
export const itemOf = uid => getItemByUid(String(uid || '')) || {};
export const filterAll = filterItems;
export { parseReviewDate, daysSinceReview, decayMastery, isKilledItem, scoreScheduleCandidate };
/** 距到期天数（负数=逾期）。today 只认 Date：被当作 map / filter 回调时第二个参数是下标，一律退回今天。 */
export function dueDays(item, today) {
  const due = parseReviewDate(item?.due_date);
  if (!due) return null;
  if (!(today instanceof Date) || Number.isNaN(today.getTime())) today = new Date();
  const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const dueUtc = Date.UTC(due.getFullYear(), due.getMonth(), due.getDate());
  return Math.floor((dueUtc - todayUtc) / 86400000);
}
export function practiceFilters({subject='',category='',ktag='',labels=[],labelMode='any'}={}){
  return {text:'',subject,category,tag:'',knowledgeTag:ktag,labels:[...labels],labelMode,difficultyMin:0,difficultyMax:10,masteryMin:null,masteryMax:null,dueFilter:'',suspended:'',sort:'none'};
}
export const filterPractice = (items,filters) => filterItems(Array.isArray(items)?items:[],practiceFilters(filters));
const zh = (a, b) => a.localeCompare(b, 'zh-CN');
const uniq = values => [...new Set(values.filter(Boolean))].sort(zh);

export function facets(items) {
  const list = Array.isArray(items) ? items : [];
  return {
    subjects: uniq(list.map(item => item.subject)),
    categories: uniq(list.map(item => item.category)),
    ktags: uniq(list.flatMap(item => item.knowledge_tags || [])),
  };
}
