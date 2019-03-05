import sys
import arrow
import utils
import numpy as np
import tensorflow as tf

from tfgen import SpatialTemporalHawkes, MarkedSpatialTemporalLSTM

class MLE_Hawkes_Generator(object):
    """
    Reinforcement Learning Based Point Process Generator
    """

    def __init__(self, T, S, batch_size, C=1., data_dim=3, keep_latest_k=None, lr=1e-3):
        """
        Params:
        - T: the maximum time of the sequences
        - S: the space of location
        - C: the constant in diffusion kernel
        - batch_size:    batch size of the training data
        - maximum:       upper bound of the conditional intensity
        - data_dim:      data dimension (=3 by default)
        - keep_latest_k: only compute latest k points in log-likelihood calculation
        - lr:            learning rate for the SGD optimizer
        """
        self.batch_size = batch_size
        # Hawkes process
        self.hawkes     = SpatialTemporalHawkes(T, S, C=C, verbose=False)
        # input tensors: expert sequences (time, location, marks)
        self.input_seqs = tf.placeholder(tf.float32, [batch_size, None, data_dim]) # [batch_size, seq_len, data_dim]
        self.cost       = -1 * self.log_likelihood(S, keep_latest_k=keep_latest_k) / batch_size
        self.optimizer  = tf.train.GradientDescentOptimizer(lr).minimize(self.cost)

    def log_likelihood(self, S, keep_latest_k):
        """
        compute the log-likelihood of the input data given the hawkes point process. 
        """
        # log-likelihood
        loglikli = 0.
        for b in range(batch_size):
            seq       = self.input_seqs[b, :, :]
            mask_t    = tf.cast(seq[:, 0] > 0, tf.float32)
            trunc_seq = tf.boolean_mask(seq, mask_t)
            seq_len   = tf.shape(trunc_seq)[0]
            # calculate the log conditional pdf for each of data points in the sequence.
            loglikli += tf.reduce_sum(tf.scan(
                lambda a, i: self.hawkes.log_conditional_pdf(trunc_seq[:i, :], keep_latest_k=keep_latest_k),
                tf.range(1, seq_len+1), # from the first point to the last point
                initializer=np.array(0., dtype=np.float32)))
        return loglikli

    def train(self, sess, 
            epoches,               # number of epoches (how many times is the entire dataset going to be trained)
            expert_seqs,           # [n, seq_len, data_dim=3]
            pretrained=False):
        """Train the point process generator given expert sequences."""

        # initialization
        if not pretrained:
            print("[%s] parameters are initialized." % arrow.now(), file=sys.stderr)
            # initialize network parameters
            init_op = tf.global_variables_initializer()
            sess.run(init_op)

        # data configurations
        # - number of expert sequences
        n_data    = expert_seqs.shape[0]
        # - number of batches
        n_batches = int(n_data / batch_size)

        # training over epoches
        for epoch in range(epoches):
            # shuffle indices of the training samples
            shuffled_ids = np.arange(n_data)
            np.random.shuffle(shuffled_ids)

            # training over batches
            avg_train_cost = []
            for b in range(n_batches):
                idx              = np.arange(batch_size * b, batch_size * (b + 1))
                # training and testing indices selected in current batch
                batch_train_ids  = shuffled_ids[idx]
                # training and testing batch data
                batch_train_seqs = expert_seqs[batch_train_ids, :, :]
                # optimization procedure
                sess.run(self.optimizer, feed_dict={self.input_seqs: batch_train_seqs})
                # cost for train batch and test batch
                train_cost = sess.run(self.cost, feed_dict={self.input_seqs: batch_train_seqs})
                # print("[%s] batch training cost: %.2f." % (arrow.now(), train_cost), file=sys.stderr)
                # record cost for each batch
                avg_train_cost.append(train_cost)

            # training log output
            avg_train_cost = np.mean(avg_train_cost)
            print('[%s] Epoch %d (n_train_batches=%d, batch_size=%d)' % (arrow.now(), epoch, n_batches, batch_size), file=sys.stderr)
            print('[%s] Training cost:\t%f' % (arrow.now(), avg_train_cost), file=sys.stderr)

        print(sess.run([self.hawkes.mu, self.hawkes.beta, self.hawkes.sigma_x, self.hawkes.sigma_y]))

if __name__ == "__main__":
    # Unittest example
    seqs = np.load('../Spatio-Temporal-Point-Process-Simulator/results/hpp_Feb_18.npy')
    print(seqs.shape)

    # training model
    with tf.Session() as sess:
        batch_size       = 50
        epoches          = 15

        ppg = MLE_Hawkes_Generator(
            T=[0., 10.], S=[[-1., 1.], [-1., 1.]], 
            batch_size=batch_size, data_dim=3, 
            keep_latest_k=None, lr=1e-4)
        ppg.train(sess, epoches, seqs)