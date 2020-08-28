import os
import logging
import optparse
from ml import RatioEstimator
from ml import Loader


parser = optparse.OptionParser(usage="usage: %prog [opts]", version="%prog 1.0")
parser.add_option('-s', '--samples',   action='store', type=str, dest='samples',   default='dilepton', help='samples to derive weights for. Sherpa 2.2.8 ttbar dilepton')
parser.add_option('-v', '--variation', action='store', type=str, dest='variation', default='qsf', help='variation to derive weights for. default QSF down to QSF up')
parser.add_option('-n', '--nentries',  action='store', type=str, dest='nentries',  default=0, help='specify the number of events do do the training on, default None means full sample')
(opts, args) = parser.parse_args()
sample  = opts.samples
var     = opts.variation
n       = opts.nentries
loading = Loader()

if os.path.exists('data/'+ sample +'/'+ var +'/X_train_'+str(n)+'.npy'):
    x='data/'+ sample +'/'+ var +'/X_train_'+str(n)+'.npy'
    y='data/'+ sample +'/'+ var +'/y_train_'+str(n)+'.npy'
    print("Loading existing datasets ", x, y)
else:
    loading.loading(
        folder='./data/',
        plot=True,
        var = var,
        do = sample,
        randomize = False,
        save = True,
        correlation = True,
        preprocessing = True,
        nentries = n
    )
    x='data/'+ sample +'/'+ var +'/X_train_'+str(n)+'.npy'
    y='data/'+ sample +'/'+ var +'/y_train_'+str(n)+'.npy'
    print("Loading new datasets ", x, y)

estimator = RatioEstimator(
    n_hidden=(8,4,2),
    activation="relu"
)
estimator.train(
    method='carl',
    batch_size = 128,
    n_epochs = 50,
    x=x,
    y=y,
    scale_inputs = True,
)
estimator.save('models/'+ sample +'/'+ var +'_carl_'+str(n), x=x, export_model = True)
