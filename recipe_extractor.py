import numpy as np
import time
import random
import sys
import json
import string
import urllib2
keep = string.lowercase + string.digits + string.whitespace
table = string.maketrans(keep, keep)
delete = ''.join(set(string.printable) - set(keep))
from nltk.corpus import wordnet
from pattern.en import singularize, pluralize
from pint import UnitRegistry
ureg = UnitRegistry()
import sqlite3 as lite
con = lite.connect('db')
from fractions import Fraction
from os import listdir
from os.path import isfile, join
from context_extractor import *
  

def hasNumbers(inputString):
    return any(char.isdigit() for char in inputString)
  
  
def getMixedFraction(flt):
  while True:
    fractionString = str(Fraction(flt).limit_denominator(8))
    if '/' in fractionString:
      fractionNums = str(Fraction(flt).limit_denominator(8)).split('/')
      num = int(fractionNums[0])
      if '8' in fractionNums[1] or '4' in fractionNums[1] or '3' in fractionNums[1]:
        den = int(fractionNums[1])
        if num<den:
          return str(num) + "/" + str(den)
        else:
          return str(num/den) + " " + str(num-den*(num/den)) + "/" + str(den)
      else:
        flt = flt - 0.05
    else:
      return str(round(flt))
    
def getFoodFromDatabase(sentence,nutrition):
  # Remove things in parentheses
  regEx = re.compile(r'([^\(]*)\([^\)]*\) *(.*)')
  m = regEx.match(sentence)
  while m:
    sentence = m.group(1) + m.group(2)
    m = regEx.match(sentence)
  
  sentence = sentence.lower()
  sentence = sentence.replace('-',' ')
  sentence = sentence.replace(' or ',' ')
  sentence = sentence.replace(' and ',' ')
  sentence = sentence.replace(' to ',' ')
  sentence = sentence.replace(' for ',' ')
  sentence = sentence.replace('(','')
  sentence = sentence.replace(')','')
  sentence = sentence.replace('about','')
  sentence = sentence.replace('and/or','')
  sentence = sentence.replace('/','slashslash')
  # Remove puncuation
  exclude = set(string.punctuation)
  sentence = ''.join(ch for ch in sentence if ch not in exclude)
  sentence = sentence.replace('slashslash','/')
  words = sentence.split()

  for i in range(len(words)):
    if words[i][-1] == 's':
      words[i] = singularize(words[i])
    if '/' in words[i]:
      words[i]=str(ureg.parse_expression(words[i]))

  print "sentence '"+sentence+"'"
  print "The words: ", 
  print words
  
  # Determine which words are ingredients and which are measurements (quantities)
  foodWords = [False]*len(words)
  measurementWords = [False]*len(words)
  quantityExpression = "none"
  for i in range(len(words)):
    synsets = wordnet.synsets(words[i])
    try:
      foo = ureg.parse_expression(words[i])
      measurementWords[i] = True
    except:
      pass
      
    for synset in synsets:
      if "none" in quantityExpression and hasNumbers(words[i]):
        quantityExpression = words[i] + ' dimensionless'
      if i>0 and 'quantity' in synset.lexname and hasNumbers(words[i-1]):
        quantityExpression = words[i-1] + " " + words[i]
        measurementWords[i] = True
        measurementWords[i-1] = True
      if 'food' in synset.lexname or 'plant' in synset.lexname:
        if not measurementWords[i]:
          foodWords[i] = True
      if i>1 and 'quantity' in synset.lexname and hasNumbers(words[i-1]) and hasNumbers(words[i-2]):
        quantityExpression = words[i-2] + " " + words[i-1] + " " + words[i]
        measurementWords[i] = True
        measurementWords[i-1] = True
        measurementWords[i-2] = True
    
  print quantityExpression
  print words
  print measurementWords
  print foodWords
  
  # Figure out the grams
  try:
    foodGrams = ureg.parse_expression(quantityExpression).to(ureg.grams)
  except:
    try:
      mills = ureg.parse_expression(quantityExpression).to(ureg.milliliters)
      foodGrams = mills.magnitude*ureg.grams
    except:
      try:
        foodGrams = float(quantityExpression[0])*ureg.dimensionless
      except:
        foodGrams = 1*ureg.dimensionless
  print foodGrams

  
  # Generate some food search strings using the food words and the words around the food words
  possibleWords = []
  for i in range(len(words)):
    if i>0 and foodWords[i]:
      if not measurementWords[i-1]:
        possibleWords.append(words[i-1] + '* NEAR/3 ' + words[i] + '*')
    if i<len(foodWords)-1 and foodWords[i]:
      if not measurementWords[i+1]:
        possibleWords.append(words[i] + '* NEAR/3 ' + words[i+1] + '*')
  for i in range(len(foodWords)):
    if foodWords[i]:
      possibleWords.append(words[i] + '*')
  
  print possibleWords
  
  foundMatch = False
  shrt_desc = "No match"
  ndb_no = '-1'
  with con:
    cur = con.cursor()    
    for possibleWord in possibleWords:
      if not foundMatch:
        if 'baking' in possibleWord and 'soda' in possibleWord:
          possibleWord = possibleWord.replace('baking','sodium')
          possibleWord = possibleWord.replace('soda','bicarbonate')

        cur.execute('select ndb_no,long_desc,com_desc,length(com_desc)-length("'+possibleWord.replace('*','').split()[0] + '") as closest from data where com_desc match "' + possibleWord.replace('*','') + '" order by closest')

        row = cur.fetchone()
        if row is not None:
          ndb_no =  row[0].encode('utf-8')
          shrt_desc = row[1].encode('utf-8')
          com_desc = row[2].encode('utf-8')
          foundMatch = True
          break
    # search the google hits simultaneously   
    if not foundMatch:
      for possibleWord in possibleWords:
        cur.execute('select c.ndb_no,shrt_desc,google_hits,length(long_desc)-length("'+possibleWord.replace('*','').split()[0] + '") as closest from ranking as r join data as c on r.ndb_no=c.ndb_no where long_desc match "'+possibleWord+'" order by google_hits desc')

        row = cur.fetchone()
        if row is not None:
          ndb_no =  row[0].encode('utf-8')
          shrt_desc = row[1].encode('utf-8')
          foundMatch = True
          break

    if foundMatch:
      cur.execute('select price from food_des where ndb_no like "'+ndb_no+'"')
      row = cur.fetchone()
      try:
        price =  float(row[0])
      except:
        price = 0

  if not foundMatch:
    return ('No match','',quantityExpression,float(quantities[0]),nutrition,0)
  
  # Get an appropriate measurement from weights table, or if there is no grams assigned, pick something from the weights table
  measurementString = "1 dimensionless"
  measurementAmount = 1
  with con:
    cur.execute('select ndb_no,amount,msre_desc,gm_wgt,abs(gm_wgt-'+str(foodGrams.magnitude)+') as diff from weight where ndb_no like "'+ndb_no+'" order by diff')
    row = cur.fetchone()
    if row is not None:    
      if len(foodGrams.units) is 0:
        measurementAmount = float(row[1]) * float(foodGrams.magnitude)
        foodGrams = (measurementAmount*float(row[3]))*ureg.grams
        measurementString = getMixedFraction(measurementAmount) + ' ' + row[2]
      else:
        measurementAmount = float(foodGrams.magnitude) / (float(row[1]) * float(row[3]))
        measurementString = getMixedFraction(measurementAmount)  + ' ' + row[2]

  
  # Get nutrition
  nutrition = getNutrition(ndb_no,foodGrams.magnitude/100.0,nutrition)
    
  return (shrt_desc,ndb_no,measurementString,foodGrams,nutrition,price*foodGrams.magnitude)

    
def getNutrition(foodId,multiplier,nutrition):
    
  with con:
      
    cur = con.cursor()    

    cur.execute('select nutr_no,nutr_val from nutrition_data where ndb_no match "'+foodId+'"')
    
    rows = cur.fetchall()
    
    for row in rows:
      id = int(row[0])
      val = float(row[1])
      cur2 = con.cursor() 
      cur2.execute('select units,NutrDesc from nutr_def where nutr_no == "'+str(id)+'"')
      rows2 = cur2.fetchone()
      units = rows2[0]
      name = rows2[1]
      if ord(units[0])==65533:
        units = 'microgram'
      if units == 'IU':
        units = 'dimensionless'
      if name in nutrition.keys():
        nutrition[name.encode('utf-8')] = str(val*ureg.parse_expression(units)+ureg.parse_expression(nutrition[name.encode('utf-8')]))
      else:
        nutrition[name.encode('utf-8')] =str(val*ureg.parse_expression(units))
      
    
  return nutrition
      
        
  
def extract_recipe_main(url):
  totalPrice = 0
  finalString = ''
  titleString = ''
  contexts = json.load(open('context_settings.json','r'))
  mypath = 'get_google_images/images/'
  onlyfiles = [ f for f in listdir(mypath) if isfile(join(mypath,f)) ]
  snippets = get_snippets(contexts,url) 
  print snippets
  data_ingredients = snippets['ingredients']  
  data = snippets['directions']
  exclude = set(string.punctuation)
  #print '# ' + json_data['name'] + "\n"

  finalString = finalString + '# ' + titleString + '\n\n'
  finalString = finalString + '<h1>## Ingredients</h1>\n' 
  finalString = finalString + '-'*30
  finalString = finalString + "\n"
  nutrition  = {}
  start = time.time()
  for line in data_ingredients.split('\n'):
    if len(line)>2:
      finalString = finalString + line
      finalString = finalString + "\n"
      try:
        (food,foodId,measurement,grams,nutrition,price) = getFoodFromDatabase(line,nutrition)
        totalPrice = totalPrice + price
        finalString = finalString + " - "
        imageName = None
        for i in onlyfiles:
          if foodId in i:
            imageName = i
            break
        if imageName is not None:
          finalString = finalString + "<img src='http://ips.colab.duke.edu/extract_recipe/get_google_images/images/" + imageName + "' width=50>"
          print food + ": " + imageName
        finalString = finalString + str(measurement) 
        finalString = finalString + food + " (" + str(round(grams.magnitude,1)) + " grams)" + " - $" + str(round(price,2)) + "\n\n"
      except:
        pass
  end = time.time()
  print end-start

  finalString = finalString + '-'*30
  finalString = finalString + "\n"
  '''
  ingredients = ''
  for ingredient in json_data['ingredients'].split('\n'):
    print " - " + ''.join(ch for ch in ingredient if ch not in exclude)
    ingredients = ingredients + ' ' + ''.join(ch for ch in ingredient if ch not in exclude)
  '''
  finalString = finalString + "\n"
  finalString = finalString + '## Directions\n' 

  finalString = finalString + data
  finalString = finalString + "\n"
  data = data.lower()
  data = data.replace('\n',' ')
  data = data.replace('one','1')
  data = data.replace('two','2')
  data = data.replace('three','3')
  data = data.replace('four','4')
  data = data.replace('five','5')
  data = data.replace('six','6')
  data = data.replace('seven','7')
  data = data.replace('eight','8')
  data = data.replace('nine','9')
  data = data.replace('ten','10')
  data = data.replace('twenty','20')
  data = data.replace('thirty','30')
  data = data.replace('forty','40')
  data = data.replace('fifty','50')
  data = data.replace('sixty','60')
  data = data.replace('overnight','12 hours')
  data = data.replace('few minute','3 minute')
  data = data.replace('few hour','3 hour')
  data = data.replace('another minute','1 minute')
  data = data.replace('several minute','4 minute')
  data = data.replace('one more minute','1 minute')
  data = data.replace('cook until','2 minute')
  data = data.replace('-',' ')
  data = ''.join(ch for ch in data if ch not in exclude)


  dataWords =  data.split()
  timeWords = ['minute','minutes','hour','hours']
  totalTime = 0*ureg.minute
  for timeWord in timeWords:
    timeI = [i for i, x in enumerate(dataWords) if x == timeWord]
    for i in timeI:
      try:
        totalTime = totalTime + int(dataWords[i-1])*ureg.parse_expression(dataWords[i])
      except:
        pass

  data = data + ' ' + data_ingredients
  dataWords =  data.split()
  cookingTimes = {'cut':1*ureg.minute,'knead':2*ureg.minute,'chop':1*ureg.minute,'food processor':2*ureg.minute,'slice':1*ureg.minute,'assemble':1*ureg.minute,'toss':1*ureg.minute,'filet':1*ureg.minute,'stuff':1*ureg.minute}
  for key in cookingTimes.keys():
    timesInData = [i for i, x in enumerate(dataWords) if x == key]
    totalTime = totalTime + len(timesInData)*cookingTimes[key]
    if len(timesInData)>0:
      finalString = finalString + "+"
      finalString = finalString + len(timesInData)*str(cookingTimes[key])
      finalString = finalString + " for " + key + "ing."
      finalString = finalString + "\n"
    
  if totalTime > 60*ureg.minute:
    finalString = finalString + "# Calculated time: "
    finalString = finalString + str(totalTime.to(ureg.hour))
    finalString = finalString + "\n"
  else:
    finalString = finalString + "# Calculated time: "
    finalString = finalString + str(totalTime)
    finalString = finalString + "\n"
  
  finalString = finalString + "# Calculated cost: $"
  finalString = finalString + "%.2f"%totalPrice
  finalString = finalString + "\n"

  nutrition['Energy'] = str(ureg.parse_expression(nutrition['Energy']).to(ureg.kilocalorie))

  servings = int(ureg.parse_expression(nutrition['Energy']).magnitude/300)
  
  finalString = finalString +  "\n\n# Serving size is about " + str(servings) + "\n"
  
  finalString = finalString + "\n\n# Nutrition data (main)\n"
  importantNutrition = ['Energy','Protein','Total lipid (fat)','Carbohydrate, by difference','Sugars, total','Fiber, total dietary','Cholesterol']
  for key in importantNutrition:
    finalString = finalString +  key + ": " + nutrition[key]  + "\n"
  print "\n\n"
    
  finalString = finalString + "\n\n# Nutrition data (ALL)\n"
  for key in sorted(nutrition.iterkeys()):
    finalString = finalString +  key + ": " + nutrition[key]  + "\n"
    
  return finalString

print extract_recipe_main('http://www.foodnetwork.com/recipes/alton-brown/baked-macaroni-and-cheese-recipe.html')
#print extract_recipe_main('http://www.marthastewart.com/344840/soft-and-chewy-chocolate-chip-cookies')
