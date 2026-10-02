/** 题库、练习与导出的统一题目筛选与日期语义。 */
import { itemsNow } from './data.js';
import { parseDay as parseReviewDate, daysBetween, businessToday } from '../core/date.js';
export const itemsOf = data => (Array.isArray(data?.items) ? data.items : []);
function asNumber(value,fallback=0){const n=Number(value);return Number.isFinite(n)?n:fallback}
function getItems(){return [...itemsNow()]}
function getItemByUid(uid){return getItems().find(item=>item.uid===uid)||null}
const getDueDays = item => dueDays(item);
function parseCreationDate(value) {
  const text = String(value || '').trim();
  if (!text) return null;
  const date = text.length <= 10 ? parseReviewDate(text) : new Date(text);
  return date && !Number.isNaN(date.getTime()) ? date : null;
}
export function creationDateValue(item) {
  const precise = parseCreationDate(item?.created_at);
  if (precise) return precise.getTime();
  const entry = parseCreationDate(item?.entry_date);
  return entry ? entry.getTime() : null;
}
function compareCreation(a, b, direction) {
  const av = creationDateValue(a), bv = creationDateValue(b);
  if (av == null && bv == null) return String(a?.uid || '').localeCompare(String(b?.uid || ''), 'zh-CN');
  if (av == null) return 1;
  if (bv == null) return -1;
  if (av !== bv) return direction === 'desc' ? bv - av : av - bv;
  return String(a?.uid || '').localeCompare(String(b?.uid || ''), 'zh-CN');
}
export function filterItems(items,filters){
  let result=[...items];
  if(filters.suspended!=='all'&&filters.suspended!=='suspended')result=result.filter(item=>!item.suspended);
  else if(filters.suspended==='suspended')result=result.filter(item=>item.suspended);
  if(filters.text){result=result.filter(item=>[item.uid,item.subject,item.category,item.tag,...(item.knowledge_tags||[]),...(item.labels||[])].join(' ').toLowerCase().includes(filters.text))}
  if(filters.subject)result=result.filter(item=>item.subject===filters.subject);
  if(filters.category)result=result.filter(item=>item.category===filters.category);
  if(filters.tag)result=result.filter(item=>(item.tag||'').includes(filters.tag));
  if(filters.knowledgeTag)result=result.filter(item=>(item.knowledge_tags||[]).includes(filters.knowledgeTag));
  if(filters.labels?.length){result=result.filter(item=>{const values=new Set(item.labels||[]);return filters.labelMode==='all'?filters.labels.every(label=>values.has(label)):filters.labels.some(label=>values.has(label))})}
  result=result.filter(item=>asNumber(item.difficulty,0)>=(filters.difficultyMin??0)&&asNumber(item.difficulty,0)<=(filters.difficultyMax??10));
  if(filters.masteryMin!=null)result=result.filter(item=>asNumber(item.mastery,0)>=filters.masteryMin);
  if(filters.masteryMax!=null)result=result.filter(item=>asNumber(item.mastery,0)<=filters.masteryMax);
  if(filters.dueFilter){result=result.filter(item=>{const dueDays=getDueDays(item);if(dueDays===null)return false;switch(filters.dueFilter){case'overdue':return dueDays<0;case'today':return dueDays===0;case'3days':return dueDays>=0&&dueDays<=3;case'7days':return dueDays>=0&&dueDays<=7;case'future':return dueDays>0;default:return true}})}
  switch(filters.sort){
    case'none':break;
    case'mastery-desc':result.sort((a,b)=>asNumber(b.mastery,0)-asNumber(a.mastery,0));break;
    case'diff-desc':result.sort((a,b)=>asNumber(b.difficulty,0)-asNumber(a.difficulty,0));break;
    case'diff-asc':result.sort((a,b)=>asNumber(a.difficulty,0)-asNumber(b.difficulty,0));break;
    case'date-desc':result.sort((a,b)=>(b.last_review||'').localeCompare(a.last_review||''));break;
    case'due-asc':result.sort((a,b)=>(getDueDays(a)??999)-(getDueDays(b)??999));break;
    case'due-desc':result.sort((a,b)=>(getDueDays(b)??-999)-(getDueDays(a)??-999));break;
    case'created-asc':result.sort((a,b)=>compareCreation(a,b,'asc'));break;
    case'created-desc':result.sort((a,b)=>compareCreation(a,b,'desc'));break;
    default:result.sort((a,b)=>asNumber(a.mastery,0)-asNumber(b.mastery,0))
  }
  return result
}


export const allItems = getItems;
export const itemOf = uid => getItemByUid(String(uid || '')) || {};
export const filterAll = filterItems;
export { parseReviewDate };
/** 距到期天数（负数=逾期）。today 只认 Date：被当作 map / filter 回调时第二个参数是下标，一律退回今天。 */
export function dueDays(item, today) {
  const due = parseReviewDate(item?.due_date);
  if (!due) return null;
  if (!(today instanceof Date) || Number.isNaN(today.getTime())) today = businessToday();
  return daysBetween(today, due);
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
