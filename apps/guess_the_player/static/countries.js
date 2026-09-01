/* 国籍中文名。index.html 和 admin.html 共用:后台新增选手的国籍下拉
   必须和这里的键完全一致,拼错或大小写不符会同时打掉国旗和赛区判定
   (server/regions.py 的 REGION 表用同一批键,有测试守住两边同步)。

   刻意用 window.X = 而不是 const X:浏览器缓存里可能还留着抽出这张表
   之前的 app.js,它自己声明了 const COUNTRY_CN。两个顶层 const 同名会让
   第二个脚本整体 SyntaxError,页面直接白屏;属性赋值则可以被旧脚本的
   const 安全遮蔽,新旧任意组合都能跑。*/
"use strict";
window.COUNTRY_CN = {
  "Denmark":"丹麦","Sweden":"瑞典","Norway":"挪威","Finland":"芬兰","France":"法国",
  "Germany":"德国","Poland":"波兰","Czech Republic":"捷克","Czechia":"捷克",
  "Slovakia":"斯洛伐克","United Kingdom":"英国","Spain":"西班牙","Portugal":"葡萄牙",
  "Netherlands":"荷兰","Belgium":"比利时","Bosnia and Herzegovina":"波黑",
  "Serbia":"塞尔维亚","Croatia":"克罗地亚","Slovenia":"斯洛文尼亚","Montenegro":"黑山",
  "North Macedonia":"北马其顿","Macedonia":"马其顿","Bulgaria":"保加利亚",
  "Romania":"罗马尼亚","Hungary":"匈牙利","Austria":"奥地利","Switzerland":"瑞士",
  "Italy":"意大利","Greece":"希腊","Turkey":"土耳其","Türkiye":"土耳其",
  "Estonia":"爱沙尼亚","Latvia":"拉脱维亚","Lithuania":"立陶宛","Iceland":"冰岛",
  "Ireland":"爱尔兰","Luxembourg":"卢森堡","Malta":"马耳他","Kosovo":"科索沃",
  "Albania":"阿尔巴尼亚","Moldova":"摩尔多瓦","Russia":"俄罗斯","Ukraine":"乌克兰",
  "Belarus":"白俄罗斯","Kazakhstan":"哈萨克斯坦","Uzbekistan":"乌兹别克斯坦",
  "Kyrgyzstan":"吉尔吉斯斯坦","Armenia":"亚美尼亚","Georgia":"格鲁吉亚",
  "Azerbaijan":"阿塞拜疆","Tajikistan":"塔吉克斯坦","United States":"美国",
  "Canada":"加拿大","Mexico":"墨西哥","Brazil":"巴西","Argentina":"阿根廷",
  "Chile":"智利","Uruguay":"乌拉圭","Peru":"秘鲁","Colombia":"哥伦比亚",
  "Venezuela":"委内瑞拉","Ecuador":"厄瓜多尔","Paraguay":"巴拉圭","Bolivia":"玻利维亚",
  "Guatemala":"危地马拉","Costa Rica":"哥斯达黎加","Dominican Republic":"多米尼加",
  "China":"中国","Mongolia":"蒙古","South Korea":"韩国","Japan":"日本",
  "Taiwan":"中国台湾","Hong Kong":"中国香港","Singapore":"新加坡","Malaysia":"马来西亚",
  "Indonesia":"印尼","Thailand":"泰国","Vietnam":"越南","Philippines":"菲律宾",
  "India":"印度","Pakistan":"巴基斯坦","Bangladesh":"孟加拉国","Sri Lanka":"斯里兰卡",
  "Nepal":"尼泊尔","Myanmar":"缅甸","Laos":"老挝","Cambodia":"柬埔寨","Macau":"中国澳门",
  "Australia":"澳大利亚","New Zealand":"新西兰","Israel":"以色列","Jordan":"约旦",
  "Lebanon":"黎巴嫩","Saudi Arabia":"沙特","United Arab Emirates":"阿联酋",
  "Qatar":"卡塔尔","Kuwait":"科威特","Iraq":"伊拉克","Iran":"伊朗","Egypt":"埃及",
  "South Africa":"南非","Morocco":"摩洛哥","Tunisia":"突尼斯","Algeria":"阿尔及利亚",
  "Nigeria":"尼日利亚","Kenya":"肯尼亚",
};
