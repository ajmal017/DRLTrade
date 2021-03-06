#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2020/7/9 0009 10:11
# @Author  : Hadrianl 
# @File    : PPO


import gym
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.distributions import Categorical
import time
import numpy as np
from collections import defaultdict

# Hyperparameters
learning_rate = 0.0001
gamma = 0.98
lmbda = 0.95
eps_clip = 0.1
K_epoch = 2
T_horizon = 20


class ActorCritic(nn.Module):
    def __init__(self, state_dim, action_dim):
        super().__init__()
        self.data = defaultdict(list)

        self.fc_1 = nn.Linear(state_dim, 64)
        self.lstm = nn.LSTM(64, 32)
        self.fc_actor = nn.Linear(32, action_dim)
        self.fc_critic = nn.Linear(32, 1)

        self.optimizer = optim.Adam(self.parameters(), lr=learning_rate)

    def act(self, x, hidden):
        x = F.relu(self.fc_1(x))
        x = x.view(-1, 1, 64)
        x, lstm_hidden = self.lstm(x, hidden)
        x = self.fc_actor(x)
        prob = F.softmax(x, dim=2)
        return prob, lstm_hidden

    def criticize(self, x, hidden):
        x = F.relu(self.fc_1(x))
        x = x.view(-1, 1, 64)
        x, _ = self.lstm(x, hidden)
        v = self.fc_critic(x)
        return v

    def put_data(self, transition):
        _iter = iter(transition)
        self.data['state'].append(next(_iter))
        self.data['action'].append(next(_iter))
        self.data['reward'].append(next(_iter))
        self.data['next_state'].append(next(_iter))
        self.data['action_prob'].append(next(_iter))
        self.data['hidden_in'].append(next(_iter))
        self.data['hidden_out'].append(next(_iter))
        self.data['isDone'].append(next(_iter))

    def get_batch(self):
        state = torch.tensor(self.data['state'], dtype=torch.float)
        action = torch.tensor([self.data['action']]).T
        reward = torch.tensor([self.data['reward']]).T
        next_state = torch.tensor(self.data['next_state'], dtype=torch.float)
        action_prob = torch.tensor([self.data['action_prob']]).T
        isDone = torch.tensor([self.data['isDone']]).T

        return state, action, reward, next_state, action_prob, \
               self.data['hidden_in'][0], self.data['hidden_out'][0], isDone

    def clear_data(self):
        self.data = defaultdict(list)

    def update_net(self):
        state, action, reward, next_state, action_prob, (h1_in, h2_in), (h1_out, h2_out), isDone = self.get_batch()
        self.clear_data()
        first_hidden = (h1_in.detach(), h2_in.detach())
        second_hidden = (h1_out.detach(), h2_out.detach())

        for i in range(K_epoch):
            v_next_state = self.criticize(next_state, second_hidden).squeeze(1)
            td_target = reward + gamma * v_next_state * isDone
            v_state = self.criticize(state, first_hidden).squeeze(1)
            delta = td_target - v_state
            delta = delta.detach().numpy()

            advantages = []
            advantage = 0
            for item in delta[::-1]:
                advantage = gamma * lmbda * advantage + item[0]
                advantages.append(advantage)
            advantages = reversed(torch.tensor([advantages], dtype=torch.float).T)

            pi, _ = self.act(state, first_hidden)
            pi_action = pi.squeeze(1).gather(1, action)

            ratio = torch.exp(torch.log(pi_action) - torch.log(action_prob))

            surrogate1 = ratio * advantages
            surrogate2 = torch.clamp(ratio, 1-eps_clip, 1+eps_clip) * advantages
            action_loss = -torch.min(surrogate1, surrogate2)

            loss = action_loss + F.smooth_l1_loss(v_state, td_target.detach())

            self.optimizer.zero_grad()
            loss.mean().backward(retain_graph=True) # backward K_epoch, so retain the graph
            self.optimizer.step()

