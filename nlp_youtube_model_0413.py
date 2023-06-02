# -*- coding: utf-8 -*-
"""NLP youtube model 0413.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/19mNhE2y-JacjSGv5b3VMrO3scA-R3T07
"""

import os

os.mkdir('squad')

url = 'https://rajpurkar.github.io/SQuAD-explorer/dataset/'

import requests

for file in ['train-v2.0.json','dev-v2.0.json']:
    res = requests.get(f'{url}{file}')  #make request
    with open (f'squad/{file}','wb') as f:
        for chunk in res.iter_content(chunk_size = 4):
            f.write(chunk)

#res

"""### **Data prep**"""

import json

with open('squad/train-v2.0.json','rb') as f:
    squad_dict = json.load(f)

def read_squad(path):
    with open(path,'rb') as f:
        squad_dict = json.load(f)
    
    contexts = []
    questions = []
    answers = []


    for group in squad_dict['data']:
        for passage in group['paragraphs']:
            context = passage['context']
            for qa in passage['qas']:
                question = qa['question']
                if 'plausible_answers' in qa.keys():
                    access = 'plausible_answers'
                else:
                    access = 'answers'
                for answer in qa[access]:
                    contexts.append(context)
                    questions.append(question)
                    answers.append(answer)
    
    return contexts,questions,answers

train_contexts,train_questions, train_answers = read_squad('squad/train-v2.0.json')
val_contexts,val_questions, val_answers = read_squad('squad/dev-v2.0.json')

#train_contexts[:2]

#val_contexts[:2]

#train_answers[0]

def add_end_idx(answers,contexts):
    for answer, context in zip(answers,contexts):
        gold_text = answer['text']
        start_idx = answer['answer_start']
        end_idx = start_idx + len(gold_text)
        
        if context[start_idx:end_idx] == gold_text:
            answer['answer_end'] = end_idx
        else:
            for n in [1,2]:
                if context[start_idx - n:end_idx - n] == gold_text:
                    answer['answer_start'] = start_idx - n
                    answer['answer_end'] = end_idx - n

                    
add_end_idx(train_answers, train_contexts)
add_end_idx(val_answers, val_contexts)

#train_answers[:5]

"""### **Tokenize Encode**"""

!pip install transformers
from transformers import DistilBertTokenizerFast

tokenizer = DistilBertTokenizerFast.from_pretrained('distilbert-base-uncased')

train_encodings = tokenizer(train_contexts, train_questions, truncation = True, padding = True)
val_encodings = tokenizer(train_contexts, train_questions, truncation = True, padding = True)

#train_encodings['input_ids'][0]

def add_token_positions(encodings, answers):
    start_positions = []
    end_positions = []
    for i in range(len(answers)):
        start_positions.append(encodings.char_to_token(i, answers[i]['answer_start']))
        end_positions.append(encodings.char_to_token(i, answers[i]['answer_end']))
        if start_positions[-1] is None:
          start_positions[-1] = tokenizer.model_max_length
        go_back = 1
        while end_positions[-1] is None:
          end_positions[-1] = encodings.char_to_token(i,train_answers[i]['answer_end']-go_back)
          go_back+=1
    encodings.update({
        'start_positions':start_positions,
        'end_positions':end_positions
    })
    
add_token_positions(train_encodings, train_answers)
add_token_positions(val_encodings, val_answers)

import torch

class SquadDataset(torch.utils.data.Dataset):
    def __init__(self,encodings):
        self.encodings = encodings
    def __getitem__(self, idx):
        return {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
    def __len__(self):
        return len(self.encodings.input_ids)

train_dataset = SquadDataset(train_encodings)
val_dataset = SquadDataset(val_encodings)

"""### **Fine Tune**"""

from transformers import DistilBertForQuestionAnswering
model = DistilBertForQuestionAnswering.from_pretrained('distilbert-base-uncased')

from torch.utils.data import DataLoader
from transformers import AdamW
from tqdm import tqdm

device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
model.to(device)
model.train()
optim = AdamW(model.parameters(), lr = 5e-5)

train_loader = DataLoader(train_dataset, batch_size = 16, shuffle = True)

#train_encodings.keys()

for epoch in range(3):
  loop = tqdm(train_loader)
  for batch in loop:
    optim.zero_grad()

    input_ids = batch['input_ids'].to(device)
    attention_mask = batch['attention_mask'].to(device)
    start_positions = batch['start_positions'].to(device)
    end_positions = batch['end_positions'].to(device)

    outputs = model(input_ids, attention_mask = attention_mask,
            start_positions = start_positions, end_positions = end_positions)
    
    loss = outputs[0]
    loss.backward()
    optim.step()

    loop.set_description(f'Epoch {epoch}')
    loop.set_postfix(loss = loss.item())

model_path = 'model/distilbert-custom'
model.save_pretrained(model_path)
tokenizer.save_pretrained(model_path)

model.eval()

val_loader = DataLoader(val_dataset, batch_size = 16)
acc = []

loop = tqdm(val_loader)
for batch in loop:
  with torch.no_grad():
    input_ids = batch['input_ids'].to(device)
    attention_mask = batch['attention_mask'].to(device)
    start_true = batch['start_positions'].to(device)
    end_true = batch['end_positions'].to(device)

    outputs = model(input_ids, attention_mask = attention_mask)
      
    start_pred = torch.argmax(outputs['start_logits'],dim=1)
    end_pred = torch.argmax(outputs['end_logits'],dim=1)

    acc.append(((start_pred == start_true).sum()/len(start_pred)).item())
    acc.append(((end_pred == end_true).sum()/len(end_pred)).item())

sum(acc)/len(acc)
#total accuracy

#acc[-1]

#start_true

#start_pred