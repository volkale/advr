import arviz as az
import numpy as np
import os
import pystan
from prepare_data import get_model_input_df

from lib.plot_utils import display_hpd
from lib.stan_utils import compile_model
import matplotlib.pyplot as plt
import seaborn as sns

# set path to stan model files
dir_name = os.path.dirname(os.path.abspath(__file__))
parent_dir_name = os.path.dirname(dir_name)
stan_model_path = os.path.join(dir_name, 'stan_models')
# investigate correlation between lnMean and lnSD


def get_varying_intercept_model_results():
    # read in Cipriani data
    df = get_model_input_df(only_placebo_controled=False)
    data_dict = {
        'N': df.shape[0],
        'Y_meas': df['lnSD'].values,
        'X_meas': df['lnMean'].values,
        'SD_Y': np.sqrt(df['var_lnSD'].values),
        'SD_X': np.sqrt(df['var_lnMean'].values),
        'K': len(df.scale.unique()),
        'scale_group': df.scale_rank.values
    }
    varying_intercept_stan_model = compile_model(
        os.path.join(stan_model_path, 'varying_intercept_regression.stan'),
        model_name='varying_intercept_regression'
    )
    fit = varying_intercept_stan_model.sampling(
        data=data_dict,
        iter=4000,
        warmup=1000,
        chains=3,
        control={'adapt_delta': 0.99},
        check_hmc_diagnostics=True,
        seed=1
    )
    pystan.check_hmc_diagnostics(fit)
    data = az.from_pystan(
        posterior=fit,
        posterior_predictive=['Y_pred'],
        observed_data=['X_meas', 'Y_meas'],
        log_likelihood='log_lik',
    )
    return data


def plot_varying_intercept_regression_lines(data):
    df = get_model_input_df(only_placebo_controled=False)
    # data = get_varying_intercept_model_results()
    # Extracting traces (and combine all chains)
    alphas = np.reshape(
        data.posterior.alpha.values,
        (data.posterior.alpha.shape[0] * data.posterior.alpha.shape[1], data.posterior.alpha.shape[2])
    )
    beta = np.reshape(data.posterior.beta.values, (data.posterior.beta.shape[0] * data.posterior.beta.shape[1]))

    # Plotting regression line
    x_min, x_max = 1., 3.5
    x = np.linspace(x_min, x_max, 100)
    scale_list = sorted(df.scale.unique())

    #  get posterior means
    alpha_means = alphas.mean(axis=0)
    beta_mean = beta.mean()

    # Plot a subset of sampled regression lines
    np.random.shuffle(alphas)
    np.random.shuffle(beta)

    fig, axes = plt.subplots(nrows=len(scale_list), ncols=1, figsize=(10, 10), sharex=True, sharey=True)
    fig.suptitle('Fitted varying intercept regression')
    for i, scale in enumerate(scale_list):
        scale_index = scale_list.index(scale)

        # Plot mean regression line
        y = alpha_means[scale_index] + beta_mean * x
        _ = axes[i].plot(x, y, linestyle='--', alpha=0.5, color='black')
        # Plot measured data
        df_a = df.query(f'scale == "{scale}" & is_active == 1')
        df_p = df.query(f'scale == "{scale}" & is_active == 0')
        _ = axes[i].scatter(df_a.lnMean.values, df_a.lnSD.values)
        _ = axes[i].scatter(df_p.lnMean.values, df_p.lnSD.values)
        # Plot sample trace regression
        for j in range(1000):
            _ = axes[i].plot(x, alphas[j, i] + beta[j] * x, color='lightsteelblue', alpha=0.005)  # NOQA

        axes[i].set_ylabel('lnSD')
        axes[i].set_title(f'{scale}')

    plt.tight_layout()
    plt.xlabel('lnMean')
    plt.xlim(x_min, x_max)
    plt.subplots_adjust(top=0.9, bottom=0.1)

    return plt


def get_shrinkage_plot(data):
    df = get_model_input_df(only_placebo_controled=False)
    data_dict = {
        'N': df.shape[0],
        'Y_meas': df['lnSD'].values,
        'X_meas': df['lnMean'].values,
        'SD_Y': np.sqrt(df['var_lnSD'].values),
        'SD_X': np.sqrt(df['var_lnMean'].values),
        'K': len(df.scale.unique()),
        'scale_group': df.scale_rank.values
    }
    fig, axes = plt.subplots(figsize=(10, 10))
    x_meas = data_dict['X_meas']
    y_meas = data_dict['Y_meas']

    x_true_trace = np.reshape(
        data.posterior.X.values,
        (data.posterior.X.shape[0] * data.posterior.X.shape[1], data.posterior.X.shape[2])
    )
    y_true_trace = np.reshape(
        data.posterior.Y.values,
        (data.posterior.Y.shape[0] * data.posterior.Y.shape[1], data.posterior.Y.shape[2])
    )

    #  get posterior means
    x_true = x_true_trace.mean(axis=0)
    y_true = y_true_trace.mean(axis=0)

    axes.scatter(x_meas, y_meas, label='measured data of lnMean and lnSD', alpha=0.7)
    axes.scatter(x_true, y_true, label='estimated true values of lnMean and lnSD', alpha=0.7)

    for xm, ym, xt, yt in zip(x_meas, y_meas, x_true, y_true):
        axes.arrow(
            xm, ym, xt - xm, yt - ym, color='gray', linestyle='--',
            length_includes_head=True, alpha=0.4, head_width=.015
        )

    plt.tight_layout()
    plt.xlabel('lnMean')
    plt.ylabel('lnSD')
    plt.title('Shrinkage effect of Bayesian varying intercept regression')
    axes.legend(loc='upper left')

    return plt

################################################################
################################################################


def get_model_results_dict():
    df = get_model_input_df(only_placebo_controled=True)
    model_res_dict = {}

    # fixed effects meta analyses (lnVR and lnCVR)
    for model in ['fema', 'rema']:  # lnVR, # random effects meta analyses (lnVR and lnCVR)
        stan_model = compile_model(
            os.path.join(stan_model_path, f'{model}.stan'),
            model_name=model
        )
        for effect_statistic in ['lnVR', 'lnCVR']:
            data_dict = {
                'N': len(df.study_id.unique()),
                'Y': df.groupby(['study_id']).agg({effect_statistic: 'first'}).reset_index()[effect_statistic].values,
                'SD_Y': np.sqrt(df.groupby(['study_id']).agg(
                    {f'var_{effect_statistic}': 'first'}).reset_index()[f'var_{effect_statistic}'].values),
                'run_estimation': 1
            }

            fit = stan_model.sampling(
                data=data_dict,
                iter=4000,
                warmup=1000,
                chains=3,
                control={'adapt_delta': 0.99},
                check_hmc_diagnostics=True,
                seed=1
            )

            data = az.from_pystan(
                posterior=fit,
                posterior_predictive=['Y_pred'],
                observed_data=['Y'],
                log_likelihood='log_lik',
            )

            model_res_dict[f'{model}_{effect_statistic}'] = data

    model = 'remr'
    stan_model = compile_model(
        os.path.join(stan_model_path, f'{model}.stan'),
        model_name=model
    )
    effect_statistic = 'lnVR'
    data_dict = {
        'N': len(df.study_id.unique()),
        'Y_meas': df.groupby(['study_id']).agg({effect_statistic: 'first'}).reset_index()[effect_statistic].values,
        'X_meas': df.groupby(['study_id']).agg({'lnRR': 'first'}).reset_index()['lnRR'].values,
        'SD_Y': np.sqrt(df.groupby(['study_id']).agg(
            {f'var_{effect_statistic}': 'first'}).reset_index()[f'var_{effect_statistic}'].values),
        'SD_X': np.sqrt(df.groupby(['study_id']).agg(
            {'var_lnRR': 'first'}).reset_index()['var_lnRR'].values),
        'run_estimation': 1
    }

    fit = stan_model.sampling(
        data=data_dict,
        iter=4000,
        warmup=1000,
        chains=3,
        control={'adapt_delta': 0.99},
        check_hmc_diagnostics=True,
        seed=1
    )
    pystan.check_hmc_diagnostics(fit)

    data = az.from_pystan(
        posterior=fit,
        posterior_predictive=['Y_pred'],
        observed_data=['Y_meas', 'X_meas'],
        log_likelihood='log_lik',
    )

    model_res_dict[f'{model}_{effect_statistic}'] = data
    return model_res_dict


def plot_model_comparison(model_res_dict):
    # model_res_dict = get_model_results_dict()
    model_compare = az.compare(model_res_dict, seed=1, scale='log', ic='waic')
    az.plot_compare(model_compare, plot_ic_diff=False, plot_standard_error=True, insample_dev=False)
    plt.savefig(os.path.join(parent_dir_name, f'output/waic_model_comparison.png'))


##############################################
##############################################


def plot_posterior_exp_mu(model_res_dict):
    for effect_stat in ['VR', 'CVR']:
        fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(10, 4), sharex=True, sharey=True)
        for ind, model in enumerate([f'fema_ln{effect_stat}', f'rema_ln{effect_stat}']):
            plt.suptitle(
                f'posterior density of {effect_stat} parameter for fixed effect and random effects models'
            )
            data = model_res_dict[model]
            chains = len(data.posterior.mu.chain)
            draws = len(data.posterior.mu.draw)
            mcmc_values = np.exp(data.posterior.mu.values.reshape(chains * draws))
            sns.distplot(
                mcmc_values,
                ax=axes[ind], label=f'{model}'.strip(f'_ln{effect_stat}').upper(), hist=False
            )
            axes[ind].set_xlabel('$\exp(\mu)$')
            axes[ind].legend(loc='upper right')
            display_hpd(axes[ind], mcmc_values, credible_interval=0.95)
        plt.subplots_adjust(top=0.9, bottom=0.1)
        plt.savefig(os.path.join(parent_dir_name, f'output/posterior_exm_mu_{model}.png'))