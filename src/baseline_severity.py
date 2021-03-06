import arviz as az
import numpy as np
import os
import pystan
import matplotlib.pyplot as plt

from lib.stan_utils import compile_model, get_pickle_filename, get_model_code
from prepare_data import (
    get_formatted_data, add_rank_column, aggregate_treatment_arms, get_variability_effect_sizes
)


# set path to stan model files
dir_name = os.path.dirname(os.path.abspath(__file__))
parent_dir_name = os.path.dirname(dir_name)
stan_model_path = os.path.join(dir_name, 'stan_models')


def prepare_data():
    df = get_formatted_data()
    df = df.query('is_placebo_controlled==1 and has_mean_pre==1 and known_max_value==1')
    df = aggregate_treatment_arms(df)
    df = get_variability_effect_sizes(df)
    df['mean_pre'] = df.mean_pre.astype(float)
    df = df.query('mean_pre > 0')
    return df


def get_baseline_severity_model():
    df = prepare_data()

    effect_statistic = 'lnVR'
    data_dict = {
        'N': len(df.study_id.unique()),
        'Y_meas': df.groupby(['study_id']).agg({effect_statistic: 'first'}).reset_index()[effect_statistic].values,
        'X_meas': df.groupby(['study_id']).agg({'lnRR': 'first'}).reset_index()['lnRR'].values,
        'SD_Y': np.sqrt(df.groupby(['study_id']).agg(
            {f'var_{effect_statistic}': 'first'}).reset_index()[f'var_{effect_statistic}'].values),
        'SD_X': np.sqrt(df.groupby(['study_id']).agg(
            {'var_lnRR': 'first'}).reset_index()['var_lnRR'].values),
        'X0': df.groupby(['study_id']).apply(
            lambda x: np.sum(x['baseline'] * x['N']) / np.sum(x['N'])
        ).reset_index()[0].values,
        'run_estimation': 1
    }

    stan_model = compile_model(
        os.path.join(stan_model_path, 'remr_bs.stan'),
        model_name='remr_bs'
    )

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
        observed_data=['Y_meas', 'X_meas', 'X0'],
        log_likelihood='log_lik',
    )
    return data


def get_baseline_severity_posterior_plot(data):
    mu_trace = np.reshape(
        data.posterior.mu.values,
        (data.posterior.mu.shape[0] * data.posterior.mu.shape[1], 1)
    )
    beta_trace = np.reshape(
        data.posterior.beta.values,
        (data.posterior.beta.shape[0] * data.posterior.beta.shape[1], 1)
    )
    gamma_trace = np.reshape(
        data.posterior.gamma.values,
        (data.posterior.gamma.shape[0] * data.posterior.gamma.shape[1], 1)
    )
    df = prepare_data()
    norm_baseline_severity = np.linspace(
        df.baseline.min(), df.baseline.max(),
        100
    )

    fig, axes = plt.subplots(nrows=3, sharex=True, sharey=True, figsize=(10, 10))
    plt.xlabel('Baseline severity on HAMD 17 scale')
    axes[0].set_title('posterior samples')
    axes[1].set_ylabel('meta analytic mean VR')
    for i, lnRR in enumerate([0, 0.25, 0.5]):
        ax = axes[i]
        y = mu_trace + gamma_trace * norm_baseline_severity + beta_trace * lnRR
        _ = ax.plot(
            norm_baseline_severity, np.exp(y[0]), color='lightsteelblue', alpha=0.5, label=f'RR={np.exp(lnRR):.1f}'
        )
        for j in range(1, 500):
            _ = ax.plot(norm_baseline_severity, np.exp(y[j]), color='lightsteelblue', alpha=0.5)  # NOQA
        y = mu_trace.mean() + gamma_trace.mean() * norm_baseline_severity + beta_trace.mean() * lnRR
        _ = ax.plot(norm_baseline_severity, np.exp(y), color='black', alpha=0.5)  # NOQA
        ax.legend(loc='upper left')

    locs, labels = plt.xticks()
    plt.setp(axes, xticks=locs[1:-1], xticklabels=[int(round(52 * x, 0)) for x in locs[1:-1]])

    plt.savefig(os.path.join(parent_dir_name, f'output/baseline_severity.tiff'), format='tiff', dpi=500,
                bbox_inches="tight")
    return plt
