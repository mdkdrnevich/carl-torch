from __future__ import absolute_import, division, print_function

import logging
import os
import json
import numpy as np
import torch

from .tools import create_missing_folders, load_and_check

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError

logger = logging.getLogger(__name__)
class Estimator(object):
    """
    Abstract class for any ML estimator. 
    Each instance of this class represents one neural estimator. The most important functions are:
    * `Estimator.train()` to train an estimator.
    * `Estimator.evaluate()` to evaluate the estimator.
    * `Estimator.save()` to save the trained model to files.
    * `Estimator.load()` to load the trained model from files.
    Please see the tutorial for a detailed walk-through.
    """

    def __init__(self, features=None, n_hidden=(100,), activation="tanh", dropout_prob=0.0):
        self.features = features
        self.n_hidden = n_hidden
        self.activation = activation
        self.dropout_prob = dropout_prob

        self.model = None
        self.n_observables = None
        self.n_parameters = None
        self.x_scaling_means = None
        self.x_scaling_stds = None

    def train(self, *args, **kwargs):
        raise NotImplementedError


    def evaluate_log_likelihood_ratio(self, *args, **kwargs):
        """
        Log likelihood ratio estimation. Signature depends on the type of estimator. The first returned value is the log
        likelihood ratio with shape `(n_thetas, n_x)` or `(n_x)`.
        """
        raise NotImplementedError

    def evaluate(self, *args, **kwargs):
        raise NotImplementedError

    def save(self, filename, save_model=False):

        """
        Saves the trained model to four files: a JSON file with the settings, a pickled pyTorch state dict
        file, and numpy files for the mean and variance of the inputs (used for input scaling).
        Parameters
        ----------
        filename : str
            Path to the files. '_settings.json' and '_state_dict.pl' will be added.
        save_model : bool, optional
            If True, the whole model is saved in addition to the state dict. This is not necessary for loading it
            again with Estimator.load(), but can be useful for debugging, for instance to plot the computational graph.
        Returns
        -------
            None
        """

        logger.info("Saving model to %s", filename)

        if self.model is None:
            raise ValueError("No model -- train or load model before saving!")

        # Check paths
        create_missing_folders([os.path.dirname(filename)])

        # Save settings
        logger.debug("Saving settings to %s_settings.json", filename)

        settings = self._wrap_settings()

        with open(filename + "_settings.json", "w") as f:
            json.dump(settings, f)

        # Save scaling
        if self.x_scaling_stds is not None and self.x_scaling_means is not None:
            logger.debug("Saving input scaling information to %s_x_means.npy and %s_x_stds.npy", filename, filename)
            np.save(filename + "_x_means.npy", self.x_scaling_means)
            np.save(filename + "_x_stds.npy", self.x_scaling_stds)

        # Save state dict
        logger.debug("Saving state dictionary to %s_state_dict.pt", filename)
        torch.save(self.model.state_dict(), filename + "_state_dict.pt")

        # Save model
        if save_model:
            logger.debug("Saving model to %s_model.pt", filename)
            torch.save(self.model, filename + "_model.pt")

    def load(self, filename):

        """
        Loads a trained model from files.
        Parameters
        ----------
        filename : str
            Path to the files. '_settings.json' and '_state_dict.pl' will be added.
        Returns
        -------
            None
        """

        logger.info("Loading model from %s", filename)

        # Load settings and create model
        logger.debug("Loading settings from %s_settings.json", filename)
        with open(filename + "_settings.json", "r") as f:
            settings = json.load(f)
        self._unwrap_settings(settings)
        self._create_model()

        # Load scaling
        try:
            self.x_scaling_means = np.load(filename + "_x_means.npy")
            self.x_scaling_stds = np.load(filename + "_x_stds.npy")
            logger.debug(
                "  Found input scaling information: means %s, stds %s", self.x_scaling_means, self.x_scaling_stds
            )
        except FileNotFoundError:
            logger.warning("Scaling information not found in %s", filename)
            self.x_scaling_means = None
            self.x_scaling_stds = None

        # Load state dict
        logger.debug("Loading state dictionary from %s_state_dict.pt", filename)
        self.model.load_state_dict(torch.load(filename + "_state_dict.pt", map_location="cpu"))

    def initialize_input_transform(self, x, transform=True, overwrite=True):
        if self.x_scaling_stds is not None and self.x_scaling_means is not None and not overwrite:
            logger.info(
                "Input rescaling already defined. To overwrite, call initialize_input_transform(x, overwrite=True)."
            )
        elif transform:
            logger.info("Setting up input rescaling")
            self.x_scaling_means = np.mean(x, axis=0)
            self.x_scaling_stds = np.maximum(np.std(x, axis=0), 1.0e-6)
        else:
            logger.info("Disabling input rescaling")
            n_parameters = x.shape[0]

            self.x_scaling_means = np.zeros(n_parameters)
            self.x_scaling_stds = np.ones(n_parameters)

    def _transform_inputs(self, x):
        if self.x_scaling_means is not None and self.x_scaling_stds is not None:
            if isinstance(x, torch.Tensor):
                x_scaled = x - torch.tensor(self.x_scaling_means, dtype=x.dtype, device=x.device)
                x_scaled = x_scaled / torch.tensor(self.x_scaling_stds, dtype=x.dtype, device=x.device)
            else:
                x_scaled = x - self.x_scaling_means
                x_scaled /= self.x_scaling_stds
        else:
            x_scaled = x
        return x_scaled

    def _wrap_settings(self):
        settings = {
            "n_observables": self.n_observables,
            "n_parameters": self.n_parameters,
            "features": self.features,
            "n_hidden": list(self.n_hidden),
            "activation": self.activation,
            "dropout_prob": self.dropout_prob,
        }
        return settings

    def _unwrap_settings(self, settings):
        try:
            _ = str(settings["estimator_type"])
        except KeyError:
            raise RuntimeError(
                "Can't find estimator type information in file. Maybe this file was created with"
                " an incompatible MadMiner version < v0.3.0?"
            )

        self.n_observables = int(settings["n_observables"])
        self.n_parameters = int(settings["n_parameters"])
        self.n_hidden = tuple([int(item) for item in settings["n_hidden"]])
        self.activation = str(settings["activation"])
        self.features = settings["features"]
        if self.features == "None":
            self.features = None
        if self.features is not None:
            self.features = list([int(item) for item in self.features])

        try:
            self.dropout_prob = float(settings["dropout_prob"])
        except KeyError:
            self.dropout_prob = 0.0
            logger.info(
                "Can't find dropout probability in model file. Probably this file was created with an older"
            )

    def _create_model(self):
        raise NotImplementedError


class ConditionalEstimator(Estimator):

    """
    Adds functionality to rescale parameters.
    """

    def __init__(self, features=None, n_hidden=(100,), activation="tanh", dropout_prob=0.0):
        super(ConditionalEstimator, self).__init__(features, n_hidden, activation, dropout_prob)

        self.theta_scaling_means = None
        self.theta_scaling_stds = None

    def save(self, filename, save_model=False):

        """
        Saves the trained model to four files: a JSON file with the settings, a pickled pyTorch state dict
        file, and numpy files for the mean and variance of the inputs (used for input scaling).
        Parameters
        ----------
        filename : str
            Path to the files. '_settings.json' and '_state_dict.pl' will be added.
        save_model : bool, optional
            If True, the whole model is saved in addition to the state dict. This is not necessary for loading it
            again with Estimator.load(), but can be useful for debugging, for instance to plot the computational graph.
        Returns
        -------
            None
        """

        super(ConditionalEstimator, self).save(filename, save_model)

        # Save param scaling
        if self.theta_scaling_stds is not None and self.theta_scaling_means is not None:
            logger.debug(
                "Saving parameter scaling information to %s_theta_means.npy and %s_theta_stds.npy", filename, filename
            )
            np.save(filename + "_theta_means.npy", self.theta_scaling_means)
            np.save(filename + "_theta_stds.npy", self.theta_scaling_stds)

    def load(self, filename):

        """
        Loads a trained model from files.
        Parameters
        ----------
        filename : str
            Path to the files. '_settings.json' and '_state_dict.pl' will be added.
        Returns
        -------
            None
        """

        super(ConditionalEstimator, self).load(filename)

        # Load param scaling
        try:
            self.theta_scaling_means = np.load(filename + "_theta_means.npy")
            self.theta_scaling_stds = np.load(filename + "_theta_stds.npy")
            logger.debug(
                "  Found parameter scaling information: means %s, stds %s",
                self.theta_scaling_means,
                self.theta_scaling_stds,
            )
        except FileNotFoundError:
            logger.warning("Parameter scaling information not found in %s", filename)
            self.theta_scaling_means = None
            self.theta_scaling_stds = None

    def initialize_parameter_transform(self, theta, transform=True, overwrite=True):
        if self.x_scaling_stds is not None and self.x_scaling_means is not None and not overwrite:
            logger.info(
                "Parameter rescaling already defined. To overwrite, call initialize_parameter_transform(theta, overwrite=True)."
            )
        elif transform:
            logger.info("Setting up parameter rescaling")
            self.theta_scaling_means = np.mean(theta, axis=0)
            self.theta_scaling_stds = np.maximum(np.std(theta, axis=0), 1.0e-6)
        else:
            logger.info("Disabling parameter rescaling")
            self.theta_scaling_means = None
            self.theta_scaling_stds = None

    def _transform_parameters(self, theta):
        if self.theta_scaling_means is not None and self.theta_scaling_stds is not None:
            if isinstance(theta, torch.Tensor):
                theta_scaled = theta - torch.tensor(self.theta_scaling_means, dtype=theta.dtype, device=theta.device)
                theta_scaled = theta_scaled / torch.tensor(
                    self.theta_scaling_stds, dtype=theta.dtype, device=theta.device
                )
            else:
                theta_scaled = theta - self.theta_scaling_means[np.newaxis, :]
                theta_scaled /= self.theta_scaling_stds[np.newaxis, :]
        else:
            theta_scaled = theta
        return theta_scaled
