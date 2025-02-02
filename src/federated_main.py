import os
import copy
import time
import pickle
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
import matplotlib

import torch
from tensorboardX import SummaryWriter

from options import args_parser
from update import LocalUpdate, test_inference
from model import CNN
from utils import get_dataset, average_weights, exp_details


if __name__ == '__main__':
    start_time = time.time()

    # define paths
    path_project = os.path.abspath('.')
    logger = SummaryWriter('logs')

    args = args_parser()
    exp_details(args)

    #args = args_parser()
    #args.iid = 0  # Set to Non-IID 
    #exp_details(args)

    #if args.gpu_id:
    #    torch.cuda.set_device(args.gpu_id)
    # device = 'cuda' if args.gpu else 'cpu'
    device = 'cpu'


    # load dataset and user groups
    train_dataset, test_dataset, user_groups = get_dataset(args)

    # BUILD MODEL
    global_model = CNN(args=args)

    # Set the model to train and send it to device.
    global_model.to(device)
    global_model.train()
    print(global_model)

    # copy weights
    global_weights = global_model.state_dict()

    # Training
    train_loss, train_accuracy = [], []
    val_acc_list, net_list = [], []
    cv_loss, cv_acc = [], []
    print_every = 1
    val_loss_pre, counter = 0, 0

    # Define the path for the log file
    log_file_path = 'save/fl_training_log.txt'

    # Ensure the directory exists
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    # Open the log file in write mode
    with open(log_file_path, 'w') as log_file:

        # Training loop
        for epoch in tqdm(range(args.epochs)):
            local_weights, local_losses = [], []
            print(f'\n | Global Training Round : {epoch+1} |\n')
            log_file.write(f'\n | Global Training Round : {epoch+1} |\n')

            global_model.train()
            m = max(int(args.frac * args.num_users), 1)
            idxs_users = np.random.choice(range(args.num_users), m, replace=False)
            #idxs_users = np.random.choice(list(user_groups.keys()), m, replace=False)
            
            for idx in idxs_users:
                # Add these lines before the line causing the error
                # print("user_groups keys:", user_groups.keys())
                # print("idx:", idx)
                local_model = LocalUpdate(args=args, dataset=train_dataset,
                                        idxs=user_groups[idx], logger=logger)
                w, loss = local_model.update_weights(
                    model=copy.deepcopy(global_model), global_round=epoch)
                local_weights.append(copy.deepcopy(w))
                local_losses.append(copy.deepcopy(loss))

            # update global weights
            global_weights = average_weights(local_weights)

            # update global weights
            global_model.load_state_dict(global_weights)

            loss_avg = sum(local_losses) / len(local_losses)
            train_loss.append(loss_avg)

            # Calculate avg training accuracy over all users at every epoch
            list_acc, list_loss = [], []
            global_model.eval()
            for c in range(args.num_users):
                local_model = LocalUpdate(args=args, dataset=train_dataset,
                                        idxs=user_groups[idx], logger=logger)
                acc, loss = local_model.inference(model=global_model)
                list_acc.append(acc)
                list_loss.append(loss)
            train_accuracy.append(sum(list_acc)/len(list_acc))

            # print global training loss after every 'i' rounds
            if (epoch+1) % print_every == 0:
                print(f' \nAvg Training Stats after {epoch+1} global rounds:')
                print(f'Training Loss : {np.mean(np.array(train_loss))}')
                print('Train Accuracy: {:.2f}% \n'.format(100*train_accuracy[-1]))
                log_file.write(f' \nAvg Training Stats after {epoch+1} global rounds:\n')
                log_file.write(f'Training Loss : {np.mean(np.array(train_loss))}\n')
                log_file.write('Train Accuracy: {:.2f}% \n'.format(100*train_accuracy[-1]))

        # Test inference after completion of training
        test_acc, test_loss = test_inference(args, global_model, test_dataset)

        print("*" * 50)
        print(f' \n Results after {args.epochs} global rounds of training:')
        print("|---- Avg Train Accuracy: {:.2f}%".format(100*train_accuracy[-1]))
        print("|---- Test Accuracy: {:.2f}%".format(100*test_acc))
        log_file.write("*" * 50)
        log_file.write(f' \n Results after {args.epochs} global rounds of training:\n')
        log_file.write("|---- Avg Train Accuracy: {:.2f}%\n".format(100*train_accuracy[-1]))
        log_file.write("|---- Test Accuracy: {:.2f}%\n".format(100*test_acc))


    # Saving the objects train_loss and train_accuracy:
    file_name = 'save/objects/{}_{}_{}_C[{}]_iid[{}]_E[{}]_B[{}].pkl'.\
        format(args.dataset, args.model, args.epochs, args.frac, args.iid,
               args.local_ep, args.local_bs)

    with open(file_name, 'wb') as f:
        pickle.dump([train_loss, train_accuracy], f)

    print('\n Total Run Time: {0:0.4f}'.format(time.time()-start_time))

    # PLOTTING (optional)
    matplotlib.use('Agg')

    # Plot Loss curve
    plt.figure()
    plt.title('Training Loss vs Communication rounds')
    plt.plot(range(len(train_loss)), train_loss, color='r')
    plt.ylabel('Training loss')
    plt.xlabel('Communication Rounds')
    plt.savefig('save/fed_{}_{}_{}_C[{}]_iid[{}]_E[{}]_B[{}]_loss.png'.
                format(args.dataset, args.model, args.epochs, args.frac,
                       args.iid, args.local_ep, args.local_bs))
    
    # Plot Average Accuracy vs Communication rounds
    plt.figure()
    plt.title('Average Accuracy vs Communication rounds')
    plt.plot(range(len(train_accuracy)), train_accuracy, color='k')
    plt.ylabel('Average Accuracy')
    plt.xlabel('Communication Rounds')
    plt.savefig('save/fed_{}_{}_{}_C[{}]_iid[{}]_E[{}]_B[{}]_acc.png'.
                format(args.dataset, args.model, args.epochs, args.frac,
                       args.iid, args.local_ep, args.local_bs))


    # Save the model
    model_path = 'save/models/fl_model_{}_{}_{}_C[{}]_iid[{}]_E[{}]_B[{}].pth'.format(
    args.dataset, args.model, args.epochs, args.frac, args.iid,
    args.local_ep, args.local_bs)

    # Ensure the directory exists
    os.makedirs(os.path.dirname(model_path), exist_ok=True)

    # Save the model
    torch.save(global_model.state_dict(), model_path)

    print(f'Model successfully saved to {model_path}')
   
    # load the model
    # model_path = 'save/models/fl_model_{}_{}_{}_C[{}]_iid[{}]_E[{}]_B[{}].pth'.format(
    #     args.dataset, args.model, args.epochs, args.frac, args.iid,
    #     args.local_ep, args.local_bs)

    # global_model.load_state_dict(torch.load(model_path))
    # global_model.to(device)
    # print(f'Model loaded from {model_path}')